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

# PDF va rasm kutubxonalari
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
API_TOKEN = '8231142795:AAGomc74mIftY6qdpJSwlWny_yrcOniA7f4'
ADMINS = [7693087447, 6420142158 ] # Bu yerga ikkinchi admin ID'sini ham qo'shishingiz mumkin
ADMIN_PRINT_ID = 7878916781   
BASE_URL = "https://bot2-l6hj.onrender.com" 
DB_URL = "postgresql://qr_baza_user:TiEUOA70TG53kF9nvUecCWAGH938wSdN@dpg-d5cosder433s739v350g-a.oregon-postgres.render.com/qr_baza"

app = Flask(__name__)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- BAZA FUNKSIYALARI ---
def get_db_connection():
    return psycopg2.connect(DB_URL)

def get_admin_stats():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(DISTINCT owner_id) FROM qrcodes WHERE owner_id IS NOT NULL")
    u = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM qrcodes")
    q = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM qrcodes WHERE owner_id IS NOT NULL")
    c = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM scan_logs")
    s = cur.fetchone()[0]
    cur.close()
    conn.close()
    return u, q, c, s

# --- WEB SERVER ---
@app.route('/')
def home(): return "QR Admin Panel Active"

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
        
        await bot.send_document(chat_id=chat_id, document=BufferedInputFile(pdf_buf.getvalue(), filename=f"{qr_id}_{color}.pdf"),
                                caption=f"🖨 **{prefix} QR KOD**\n🆔 `{qr_id}`\n🔑 Parol: `{pwd}`", parse_mode="Markdown")
        await asyncio.sleep(0.4)
    conn.commit()
    cur.close()
    conn.close()

# --- ADMIN HANDLERS ---
@dp.message(F.text == "📊 Umumiy Statistika")
async def show_admin_stats(message: types.Message):
    if message.from_user.id in ADMINS:
        u, q, c, s = get_admin_stats()
        text = (
            "📈 **Botning umumiy holati:**\n\n"
            f"👥 Jami foydalanuvchilar: `{u}` ta\n"
            f"📦 Jami yaratilgan QRlar: `{q}` ta\n"
            f"✅ Faollashtirilgan QRlar: `{c}` ta\n"
            f"🆓 Bo'sh turgan QRlar: `{q - c}` ta\n"
            f"👁 Jami skanerlashlar: `{s}` marta"
        )
        await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "➕ Yangi QR yaratish (Admin)")
async def admin_start_gen(message: types.Message, state: FSMContext):
    if message.from_user.id in ADMINS:
        await message.answer("⚪️ **OQ** QR dan nechta? (Raqam yuboring):")
        await state.set_state(QRStates.waiting_for_white_count)

@dp.message(QRStates.waiting_for_white_count)
async def process_white(message: types.Message, state: FSMContext):
    if message.text.isdigit():
        await state.update_data(white=int(message.text))
        await message.answer("⚫️ **QORA** QR dan nechta?")
        await state.set_state(QRStates.waiting_for_black_count)

@dp.message(QRStates.waiting_for_black_count)
async def process_black(message: types.Message, state: FSMContext):
    if message.text.isdigit():
        data = await state.get_data()
        w, b = data.get('white', 0), int(message.text)
        await message.answer(f"⏳ {w+b} ta QR tayyorlanmoqda...")
        if w > 0: await generate_and_send_qr_pdf(w, "oq", ADMIN_PRINT_ID)
        if b > 0: await generate_and_send_qr_pdf(b, "qora", ADMIN_PRINT_ID)
        await message.answer("✅ Tayyor!")
        await state.clear()

# --- QR DECODER (ADMIN) ---
@dp.message(F.photo & (F.from_user.id.in_(ADMINS)))
async def decode_qr(message: types.Message):
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    file_data = await bot.download_file(file.file_path)
    file_bytes = np.asarray(bytearray(file_data.read()), dtype=np.uint8)
    img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
    data, _, _ = cv2.QRCodeDetector().detectAndDecode(img)
    if data and "/go/" in data:
        qr_id = data.split("/go/")[-1]
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=extras.DictCursor)
        cur.execute("SELECT * FROM qrcodes WHERE qr_id = %s", (qr_id,))
        res = cur.fetchone()
        if res:
            await message.answer(f"🔍 **QR Ma'lumot:**\n🆔 ID: `{res['qr_id']}`\n🔑 Parol: `{res['password']}`\n🔗 Link: {res['target_link']}")
        cur.close()
        conn.close()

# --- USER HANDLERS ---
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
            await message.answer(f"🆔 ID: {qr_id}\nParolni kiriting:")
            await state.set_state(QRStates.waiting_for_password)
        cur.close()
        conn.close()
    else:
        kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📊 Mening QR kodlarim")]], resize_keyboard=True)
        if message.from_user.id in ADMINS:
            kb.keyboard.append([KeyboardButton(text="➕ Yangi QR yaratish (Admin)")])
            kb.keyboard.append([KeyboardButton(text="📊 Umumiy Statistika")])
        await message.answer("Xush kelibsiz!", reply_markup=kb)

@dp.message(QRStates.waiting_for_password)
async def check_pwd(message: types.Message, state: FSMContext):
    data = await state.get_data()
    if message.text == data['pwd']:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE qrcodes SET owner_id = %s WHERE qr_id = %s", (message.from_user.id, data['qr_id']))
        conn.commit()
        cur.close()
        conn.close()
        await message.answer("✅ To'g'ri! Endi yangi linkni yuboring:")
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
    await message.answer(f"✅ Saqlandi: {link}")
    await state.clear()

@dp.message(F.text == "📊 Mening QR kodlarim")
async def my_qrs(message: types.Message):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=extras.DictCursor)
    cur.execute("SELECT * FROM qrcodes WHERE owner_id = %s", (message.from_user.id,))
    rows = cur.fetchall()
    if rows:
        for r in rows:
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✏️ Tahrirlash", callback_data=f"ed_{r['qr_id']}")]])
            await message.answer(f"🆔 `{r['qr_id']}`\n🔑 Parol: `{r['password']}`", reply_markup=kb)
    cur.close()
    conn.close()

def run_flask(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

async def run_bot():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    Thread(target=run_flask).start()
    asyncio.run(run_bot())
