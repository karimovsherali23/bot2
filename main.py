import os
import asyncio
import io
import random
import string
import qrcode
import psycopg2
from psycopg2 import extras
import logging
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import cv2

# PDF yaratish uchun kutubxonalar
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader

from flask import Flask, redirect, render_template_string
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from threading import Thread

# --- SOZLAMALAR ---
API_TOKEN = '8231142795:AAGubssILkVaQ-rrFBstS4tt0kJAaACQbZI'
ADMIN_ID = [7693087447, 6420142158]        
ADMIN_PRINT_ID = 7693087447   
BASE_URL = "https://bot2-l6hj.onrender.com" 
DB_URL = "postgresql://qr_baza_user:TiEUOA70TG53kF9nvUecCWAGH938wSdN@dpg-d5cosder433s739v350g-a.oregon-postgres.render.com/qr_baza"

app = Flask(__name__)

# --- BAZA BILAN ISHLASH ---
def get_db_connection():
    return psycopg2.connect(DB_URL)

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS qrcodes (
            qr_id TEXT PRIMARY KEY,
            password TEXT,
            target_link TEXT,
            owner_id BIGINT
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS scan_logs (
            id SERIAL PRIMARY KEY,
            qr_id TEXT,
            scan_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    cur.close()
    conn.close()

init_db()

# --- WEB SERVER ---
@app.route('/')
def home(): return "QR Full System with Decoder Active"

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
        bot_link = f"https://t.me/qrme1bot?start={qr_id}" # <--- Bot username o'zgartirildi
        return render_template_string(f'<script>window.location.href="{bot_link}";</script>')
    return "❌ QR Topilmadi", 404

# --- BOT QISMI ---
logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

class QRStates(StatesGroup):
    waiting_for_password = State()
    waiting_for_new_link = State()
    waiting_for_white_count = State()
    waiting_for_black_count = State()

# --- PDF GENERATSIYASI ---
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
        page_size = 80*mm
        c = canvas.Canvas(pdf_buf, pagesize=(page_size, page_size))
        qr_reader = ImageReader(img_png)
        qr_width = 70*mm
        offset = (page_size - qr_width) / 2
        c.drawImage(qr_reader, offset, offset, width=qr_width, height=qr_width, mask='auto')
        c.showPage()
        c.save()
        pdf_buf.seek(0)
        
        await bot.send_document(
            chat_id=chat_id,
            document=BufferedInputFile(pdf_buf.getvalue(), filename=f"{qr_id}_{color}.pdf"),
            caption=f"🖨 **{prefix} QR KOD (PDF)**\n🆔 `{qr_id}`\n🔑 Parol: `{pwd}`",
            parse_mode="Markdown"
        )
        await asyncio.sleep(0.5)
        
    conn.commit()
    cur.close()
    conn.close()

# --- ADMIN: QR RASMINI DEKODLASH (PAROLNI TOPISH) ---
@dp.message(F.photo & (F.from_user.id == ADMIN_ID))
async def admin_decode_qr(message: types.Message):
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    file_data = await bot.download_file(file.file_path)
    
    try:
        # Rasmni OpenCV uchun tayyorlash
        file_bytes = np.asarray(bytearray(file_data.read()), dtype=np.uint8)
        img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        
        # QR kodni aniqlash
        detector = cv2.QRCodeDetector()
        data, points, _ = detector.detectAndDecode(img)
        
        if data and "/go/" in data:
            qr_id = data.split("/go/")[-1]
            conn = get_db_connection()
            cur = conn.cursor(cursor_factory=extras.DictCursor)
            cur.execute("SELECT * FROM qrcodes WHERE qr_id = %s", (qr_id,))
            res = cur.fetchone()
            cur.close()
            conn.close()
            
            if res:
                text = (
                    f"🔍 **QR Kod tahlili:**\n\n"
                    f"🆔 ID: `{res['qr_id']}`\n"
                    f"🔑 Parol: `{res['password']}`\n"
                    f"🔗 Link: {res['target_link'] or 'Hali kiritilmagan'}\n"
                    f"👤 Egasi: `{res['owner_id'] or 'Hali biriktirilmagan'}`"
                )
                await message.answer(text, parse_mode="Markdown")
            else:
                await message.answer("❌ Bu QR ID bazada topilmadi.")
        else:
            await message.answer("⚠️ Rasmdan QR kodni o'qib bo'lmadi yoki u bizning tizimga tegishli emas.")
    except Exception as e:
        await message.answer(f"❌ Xatolik yuz berdi: {e}")

# --- ADMIN: BATCH GENERATION HANDLERS ---
@dp.message(F.text == "➕ Yangi QR yaratish (Admin)")
async def admin_start_gen(message: types.Message, state: FSMContext):
    if message.from_user.id == ADMIN_ID:
        await message.answer("⚪️ **OQ** rangli QR koddan nechta yaratish kerak? (Raqam yuboring):")
        await state.set_state(QRStates.waiting_for_white_count)

@dp.message(QRStates.waiting_for_white_count)
async def process_white_count(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Raqam kiriting!")
        return
    await state.update_data(white_count=int(message.text))
    await message.answer("⚫️ **QORA** rangli QR koddan nechta yaratish kerak?")
    await state.set_state(QRStates.waiting_for_black_count)

@dp.message(QRStates.waiting_for_black_count)
async def process_black_count(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Raqam kiriting!")
        return
    
    black_count = int(message.text)
    data = await state.get_data()
    white_count = data.get('white_count', 0)
    
    await message.answer(f"⏳ Jami {white_count + black_count} ta QR tayyorlanmoqda...")
    
    try:
        if white_count > 0:
            await generate_and_send_qr_pdf(white_count, "oq", ADMIN_PRINT_ID)
        if black_count > 0:
            await generate_and_send_qr_pdf(black_count, "qora", ADMIN_PRINT_ID)
        await message.answer("✅ Barcha PDF fayllar yuborildi.")
    except Exception as e:
        await message.answer(f"⚠️ Xatolik: {e}")
    await state.clear()

# --- FOYDALANUVCHI HANDLERLARI ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    args = message.text.split()[1:]
    if args:
        qr_id = args[0]
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT password, owner_id FROM qrcodes WHERE qr_id = %s", (qr_id,))
        res = cur.fetchone()
        cur.close()
        conn.close()
        if res and (res[1] is None or res[1] == message.from_user.id):
            await state.update_data(qr_id=qr_id, correct_password=res[0])
            await message.answer(f"🆔 QR-ID: {qr_id}\n\nParolni kiriting:")
            await state.set_state(QRStates.waiting_for_password)
    else:
        kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📊 Mening QR kodlarim")]], resize_keyboard=True)
        if message.from_user.id == ADMIN_ID:
            kb.keyboard.append([KeyboardButton(text="➕ Yangi QR yaratish (Admin)")])
        await message.answer("Xush kelibsiz!", reply_markup=kb)

@dp.message(QRStates.waiting_for_password)
async def check_pwd(message: types.Message, state: FSMContext):
    data = await state.get_data()
    if message.text == data['correct_password']:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE qrcodes SET owner_id = %s WHERE qr_id = %s", (message.from_user.id, data['qr_id']))
        conn.commit()
        cur.close()
        conn.close()
        await message.answer("✅ Parol to'g'ri! Endi yangi linkni yuboring:")
        await state.set_state(QRStates.waiting_for_new_link)
    else:
        await message.answer("❌ Parol xato!")

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
        for row in rows:
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✏️ Tahrirlash", callback_data=f"ed_{row['qr_id']}") ]])
            await message.answer(f"🆔 `{row['qr_id']}`\n🔑 Parol: `{row['password']}`", reply_markup=kb)
    cur.close()
    conn.close()

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

async def run_bot():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    Thread(target=run_flask).start()
    asyncio.run(run_bot())
