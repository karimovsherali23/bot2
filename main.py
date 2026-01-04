import os
import asyncio
import io
import random
import string
import qrcode
import psycopg2
from psycopg2 import extras
import logging
from threading import Thread
import numpy as np
import cv2
from datetime import datetime

# PDF kutubxonalari
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader

from flask import Flask, redirect, render_template_string
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# --- SOZLAMALAR ---
API_TOKEN = '8231142795:AAGkVEOF3hXHUQh-ntlx0apjk9aeosZw_UA'
ADMINS = [7693087447, 6420142158] 
ADMIN_PRINT_ID = 7878916781   
BASE_URL = "https://bot2-l6hj.onrender.com" 
DB_URL = "postgresql://qr_baza_user:TiEUOA70TG53kF9nvUecCWAGH938wSdN@dpg-d5cosder433s739v350g-a.oregon-postgres.render.com/qr_baza"

app = Flask(__name__)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- BAZA FUNKSIYALARI ---
def get_db_connection():
    return psycopg2.connect(DB_URL)

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    # QR jadvallari (qr_name ustuni qo'shildi)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS qrcodes (
            qr_id TEXT PRIMARY KEY,
            password TEXT,
            target_link TEXT,
            owner_id BIGINT,
            qr_name TEXT,
            is_premium BOOLEAN DEFAULT TRUE
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS scan_logs (
            id SERIAL PRIMARY KEY,
            qr_id TEXT,
            scan_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # Agar jadval oldindan bo'lsa, qr_name ustunini qo'shish
    try:
        cur.execute("ALTER TABLE qrcodes ADD COLUMN IF NOT EXISTS qr_name TEXT")
    except:
        pass
    conn.commit()
    cur.close()
    conn.close()

init_db()

# --- WEB SERVER (REDIRECT TIZIMI) ---
@app.route('/')
def home(): return "QR Advanced System Active"

@app.route('/go/<qr_id>')
def redirect_handler(qr_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT target_link FROM qrcodes WHERE qr_id = %s", (qr_id,))
    data = cur.fetchone()
    if data:
        cur.execute("INSERT INTO scan_logs (qr_id) VALUES (%s)", (qr_id,))
        conn.commit()
        target_link = data[0]
        cur.close()
        conn.close()
        if target_link and target_link.startswith("http"):
            return redirect(target_link)
        return render_template_string(f'<script>window.location.href="https://t.me/qrme1bot?start={qr_id}";</script>')
    return "❌ QR Topilmadi", 404

# --- STATES ---
class QRStates(StatesGroup):
    waiting_for_password = State()
    waiting_for_qr_name = State()   # Yangi holat
    waiting_for_new_link = State()
    waiting_for_white_count = State()
    waiting_for_black_count = State()

# --- PDF GENERATOR ---
async def generate_and_send_qr_pdf(count, color, chat_id):
    conn = get_db_connection()
    cur = conn.cursor()
    fill_color = "white" if color == "oq" else "black"
    prefix = "⚪️ OQ" if color == "oq" else "⚫️ QORA"
    
    for _ in range(count):
        qr_id = f"ID{random.randint(100000, 999999)}"
        pwd = ''.join(random.choices(string.digits, k=4))
        cur.execute("INSERT INTO qrcodes (qr_id, password, target_link) VALUES (%s, %s, %s)", (qr_id, pwd, ""))
        
        qr_url = f"{BASE_URL}/go/{qr_id}"
        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=20, border=2)
        qr.add_data(qr_url)
        qr.make(fit=True)
        img_png = qr.make_image(fill_color=fill_color, back_color="transparent").convert('RGBA')
        
        pdf_buf = io.BytesIO()
        c = canvas.Canvas(pdf_buf, pagesize=(80*mm, 80*mm))
        qr_reader = ImageReader(img_png)
        c.drawImage(qr_reader, 5*mm, 5*mm, width=70*mm, height=70*mm, mask='auto')
        c.showPage()
        c.save()
        pdf_buf.seek(0)
        
        await bot.send_document(
            chat_id=chat_id, 
            document=BufferedInputFile(pdf_buf.getvalue(), filename=f"{qr_id}_{color}.pdf"),
            caption=f"🖨 **{prefix} QR KOD**\n🆔 `{qr_id}`\n🔑 Parol: `{pwd}`", 
            parse_mode="Markdown"
        )
        await asyncio.sleep(0.4)
    conn.commit()
    cur.close()
    conn.close()

# --- USER: STATISTIKA ---
@dp.callback_query(F.data.startswith("stat_"))
async def show_user_qr_stats(callback: types.CallbackQuery):
    qr_id = callback.data.split("_")[1]
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=extras.DictCursor)
    try:
        cur.execute("SELECT COUNT(*) FROM scan_logs WHERE qr_id = %s", (qr_id,))
        total_scans = cur.fetchone()[0]
        if total_scans == 0:
            await callback.answer("⚠️ Bu QR kod hali skanerlanmagan.", show_alert=True)
            return
        cur.execute("SELECT scan_time FROM scan_logs WHERE qr_id = %s ORDER BY scan_time DESC LIMIT 10", (qr_id,))
        logs = cur.fetchall()
        text = f"📊 **QR STATISTIKASI (ID: {qr_id})**\n\n👁 **Jami skanerlashlar:** `{total_scans}` marta\n"
        text += "----------------------------------\n🕒 **Oxirgi faolliklar:**\n\n"
        for i, log in enumerate(logs, 1):
            time_str = log['scan_time'].strftime("%H:%M:%S | %d.%m.%Y")
            text += f"{i}. ✅ `{time_str}`\n"
        await callback.message.answer(text, parse_mode="Markdown")
        await callback.answer()
    except Exception as e:
        await callback.message.answer(f"❌ Xatolik: {e}")
    finally:
        cur.close()
        conn.close()

# --- USER: MENING QR KODLARIM (NOM BILAN) ---
@dp.message(F.text == "📊 Mening QR kodlarim")
async def my_qrs(message: types.Message):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=extras.DictCursor)
    cur.execute("SELECT * FROM qrcodes WHERE owner_id = %s", (message.from_user.id,))
    rows = cur.fetchall()
    if rows:
        for r in rows:
            qr_name = r['qr_name'] if r['qr_name'] else "Nomsiz"
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📈 Statistika", callback_data=f"stat_{r['qr_id']}")],
                [InlineKeyboardButton(text="✏️ Havolani tahrirlash", callback_data=f"ed_{r['qr_id']}")]
            ])
            await message.answer(
                f"🏷 **Nomi:** {qr_name}\n🆔 QR ID: `{r['qr_id']}`\n🔑 Parol: `{r['password']}`\n🔗 Link: {r['target_link'] or 'Kiritilmagan'}", 
                reply_markup=kb, parse_mode="Markdown"
            )
    else:
        await message.answer("Sizda hali biriktirilgan QR kodlar yo'q.")
    cur.close()
    conn.close()

# --- ADMIN FUNKSIYALARI ---
@dp.message(F.text == "➕ Yangi QR yaratish (Admin)")
async def admin_start_gen(message: types.Message, state: FSMContext):
    if message.from_user.id in ADMINS:
        await message.answer("⚪️ **OQ** QR dan nechta kerak? (Faqat raqam):")
        await state.set_state(QRStates.waiting_for_white_count)

@dp.message(QRStates.waiting_for_white_count)
async def process_white(message: types.Message, state: FSMContext):
    if message.text.isdigit():
        await state.update_data(white=int(message.text))
        await message.answer("⚫️ **QORA** QR dan nechta kerak?")
        await state.set_state(QRStates.waiting_for_black_count)

@dp.message(QRStates.waiting_for_black_count)
async def process_black(message: types.Message, state: FSMContext):
    if message.text.isdigit():
        data = await state.get_data()
        w, b = data.get('white', 0), int(message.text)
        await message.answer(f"⏳ {w+b} ta PDF tayyorlanmoqda...")
        if w > 0: await generate_and_send_qr_pdf(w, "oq", ADMIN_PRINT_ID)
        if b > 0: await generate_and_send_qr_pdf(b, "qora", ADMIN_PRINT_ID)
        await message.answer("✅ Fayllar yuborildi.")
        await state.clear()

@dp.message(F.text == "📊 Umumiy Statistika")
async def admin_global_stats(message: types.Message):
    if message.from_user.id in ADMINS:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(DISTINCT owner_id) FROM qrcodes WHERE owner_id IS NOT NULL")
        u = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM qrcodes")
        q = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM scan_logs")
        s = cur.fetchone()[0]
        cur.close()
        conn.close()
        await message.answer(f"📈 **Admin Panel**\n\n👤 Foydalanuvchilar: `{u}` ta\n📦 Jami QRlar: `{q}` ta\n👁 Jami skanerlar: `{s}` marta")

# --- START VA JARAYON ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    args = message.text.split()[1:]
    if args:
        qr_id = args[0]
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT password, owner_id FROM qrcodes WHERE qr_id = %s", (qr_id,))
        res = cur.fetchone()
        if res and (res[1] is None or res[1] == message.from_user.id):
            await state.update_data(qr_id=qr_id, pwd=res[0])
            await message.answer(f"🔑 QR ID: {qr_id}\n\nUshbu QR kodni faollashtirish uchun parolni kiriting:")
            await state.set_state(QRStates.waiting_for_password)
        cur.close()
        conn.close()
    else:
        kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📊 Mening QR kodlarim")]], resize_keyboard=True)
        if message.from_user.id in ADMINS:
            kb.keyboard.append([KeyboardButton(text="➕ Yangi QR yaratish (Admin)"), KeyboardButton(text="📊 Umumiy Statistika")])
        await message.answer("Assalomu alaykum! QR boshqaruv botiga xush kelibsiz.", reply_markup=kb)

@dp.message(QRStates.waiting_for_password)
async def check_pwd(message: types.Message, state: FSMContext):
    data = await state.get_data()
    if message.text == data['pwd']:
        await message.answer("✅ Parol to'g'ri!\n\nEndi ushbu QR kodingizga nom bering (masalan: Zara kastyum yoki Sumka):")
        await state.set_state(QRStates.waiting_for_qr_name)
    else:
        await message.answer("❌ Parol xato, qayta urinib ko'ring:")

@dp.message(QRStates.waiting_for_qr_name)
async def process_qr_name(message: types.Message, state: FSMContext):
    qr_name = message.text
    data = await state.get_data()
    qr_id = data['qr_id']
    
    conn = get_db_connection()
    cur = conn.cursor()
    # Egasini va nomini bir vaqtda saqlash
    cur.execute("UPDATE qrcodes SET owner_id = %s, qr_name = %s WHERE qr_id = %s", 
                (message.from_user.id, qr_name, qr_id))
    conn.commit()
    cur.close()
    conn.close()
    
    await message.answer(f"📝 Nom saqlandi: **{qr_name}**\n\nEndi ushbu QR uchun linkni (havolani) yuboring:")
    await state.set_state(QRStates.waiting_for_new_link)

@dp.message(QRStates.waiting_for_new_link)
async def save_link(message: types.Message, state: FSMContext):
    link = message.text if message.text.startswith("http") else f"https://{message.text}"
    data = await state.get_data()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE qrcodes SET target_link = %s WHERE qr_id = %s", (link, data['qr_id']))
    conn.commit()
    cur.close()
    conn.close()
    await message.answer(f"🚀 Tayyor! Link saqlandi.")
    await state.clear()

@dp.callback_query(F.data.startswith("ed_"))
async def edit_qr(callback: types.CallbackQuery, state: FSMContext):
    qr_id = callback.data.split("_")[1]
    await state.update_data(qr_id=qr_id)
    await callback.message.answer("Yangi havolani (link) yuboring:")
    await state.set_state(QRStates.waiting_for_new_link)

def run_flask(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

async def run_bot():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    Thread(target=run_flask).start()
    asyncio.run(run_bot())
