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
from flask import Flask, redirect, render_template_string
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from threading import Thread

# --- SOZLAMALAR ---
API_TOKEN = '8110490890:AAHTd6WduBLqjqD2lHfT62x1XnaELBQfjuY'
ADMIN_ID = 7693087447         # Siz (Buyruq beruvchi)
ADMIN_PRINT_ID = 7878916781   # BU YERGA PRINT ADMIN ID-SINI YOZING (Hozircha o'zingizniki turibdi)

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
def home(): return "QR Print System Active"

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
        bot_link = f"https://t.me/QRedit_bot?start={qr_id}"
        return render_template_string(f'<script>window.location.href="{bot_link}";</script>')
    return "❌ Topilmadi", 404

# --- BOT QISMI ---
logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

class QRStates(StatesGroup):
    waiting_for_password = State()
    waiting_for_new_link = State()
    waiting_for_batch_count = State()

# --- ADMIN PRINT FUNKSIYASI ---
@dp.message(F.text == "➕ Yangi QR yaratish (Admin)")
async def admin_ask_count(message: types.Message, state: FSMContext):
    if message.from_user.id == ADMIN_ID:
        await message.answer("🔢 Nechta QR kod yaratmoqchisiz? Miqdorni yuboring:")
        await state.set_state(QRStates.waiting_for_batch_count)

@dp.message(QRStates.waiting_for_batch_count)
async def process_batch_generation(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Faqat raqam yuboring!")
        return
    
    count = int(message.text)
    if count > 50: count = 50

    await message.answer(f"⏳ {count} ta QR kod generatsiya qilinmoqda...")
    if ADMIN_PRINT_ID != message.from_user.id:
        await bot.send_message(ADMIN_PRINT_ID, f"🔔 Asosiy admin {count} ta yangi QR yaratishni boshladi...")

    conn = get_db_connection()
    cur = conn.cursor()
    
    for _ in range(count):
        qr_id = f"ID{random.randint(100000, 999999)}"
        pwd = ''.join(random.choices(string.digits, k=4))
        
        cur.execute("INSERT INTO qrcodes (qr_id, password, target_link) VALUES (%s, %s, %s)", (qr_id, pwd, ""))
        
        qr_url = f"{BASE_URL}/go/{qr_id}"
        img = qrcode.make(qr_url)
        buf = io.BytesIO()
        img.save(buf)
        buf.seek(0)
        
        # NATIJANI FAQAT ADMIN_PRINT_ID GA YUBORAMIZ
        caption = f"🖨 **YANGI QR KOD**\n🆔 `{qr_id}`\n🔑 Parol: `{pwd}`\n🔗 {qr_url}"
        await bot.send_photo(
            chat_id=ADMIN_PRINT_ID, 
            photo=BufferedInputFile(buf.getvalue(), filename=f"{qr_id}.png"), 
            caption=caption, 
            parse_mode="Markdown"
        )
        await asyncio.sleep(0.5) # Bot bloklanib qolmasligi uchun kichik pauza
        
    conn.commit()
    cur.close()
    conn.close()
    
    await message.answer(f"✅ Tayyor! Barcha {count} ta QR kod **Admin_Print** manziliga yuborildi.")
    await state.clear()

# --- ADMIN UCHUN QR SKANER (OpenCV) ---
@dp.message(F.photo & (F.from_user.id == ADMIN_ID))
async def admin_photo_scan(message: types.Message):
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    file_data = await bot.download_file(file.file_path)
    try:
        file_bytes = np.asarray(bytearray(file_data.read()), dtype=np.uint8)
        img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        detector = cv2.QRCodeDetector()
        data, _, _ = detector.detectAndDecode(img)
        if data:
            if "/go/" in data:
                qr_id = data.split("/go/")[-1]
                conn = get_db_connection()
                cur = conn.cursor(cursor_factory=extras.DictCursor)
                cur.execute("SELECT * FROM qrcodes WHERE qr_id = %s", (qr_id,))
                res = cur.fetchone()
                cur.close()
                conn.close()
                if res:
                    await message.answer(f"🔍 **Topildi:**\n🆔 `{res['qr_id']}`\n🔑 Parol: `{res['password']}`\n👤 Egasi: `{res['owner_id'] or 'Yoq'}`", parse_mode="Markdown")
        else:
            await message.answer("❌ QR aniqlanmadi.")
    except Exception as e:
        await message.answer("⚠️ Xatolik yuz berdi.")

# --- FOYDALANUVCHI FUNKSIYALARI ---
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
        if res:
            if res[1] is None or res[1] == message.from_user.id:
                await state.update_data(qr_id=qr_id, correct_password=res[0])
                await message.answer(f"🆔 QR-ID: {qr_id}\n\nXavfsizlik uchun parolni kiriting:")
                await state.set_state(QRStates.waiting_for_password)
            else:
                await message.answer("❌ Bu QR kod band.")
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
        await message.answer("✅ To'g'ri! Endi yangi linkni yuboring:")
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
    await message.answer(f"✅ Saqlandi!\nLink: {link}")
    await state.clear()

@dp.message(F.text == "📊 Mening QR kodlarim")
async def my_qrs(message: types.Message):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=extras.DictCursor)
    cur.execute("SELECT * FROM qrcodes WHERE owner_id = %s", (message.from_user.id,))
    rows = cur.fetchall()
    if not rows:
        await message.answer("Hali QR kodlaringiz yo'q.")
    else:
        for row in rows:
            cur.execute("SELECT COUNT(*) FROM scan_logs WHERE qr_id = %s", (row['qr_id'],))
            cnt = cur.fetchone()[0]
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📈 Statistika", callback_data=f"gr_{row['qr_id']}")],
                [InlineKeyboardButton(text="✏️ Tahrirlash", callback_data=f"ed_{row['qr_id']}")]
            ])
            await message.answer(f"🆔 `{row['qr_id']}`\n🔗 Link: {row['target_link']}\n👁 Skaner: {cnt}\n🔑 Parol: `{row['password']}`", reply_markup=kb, parse_mode="Markdown")
    cur.close()
    conn.close()

# --- QOLGAN CALLBACKLAR ---
@dp.callback_query(F.data.startswith("gr_"))
async def show_gr(callback: types.CallbackQuery):
    # Bu yerda generate_stats_graph funksiyasini chaqirish kerak
    await callback.answer("Grafik generatsiya qilinmoqda...")

@dp.callback_query(F.data.startswith("ed_"))
async def ed_start(callback: types.CallbackQuery, state: FSMContext):
    qr_id = callback.data.split("_")[1]
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT password FROM qrcodes WHERE qr_id = %s", (qr_id,))
    pwd = cur.fetchone()[0]
    cur.close()
    conn.close()
    await state.update_data(qr_id=qr_id, correct_password=pwd)
    await callback.message.answer("Parolni kiring:")
    await state.set_state(QRStates.waiting_for_password)
    await callback.answer()

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

async def run_bot():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    Thread(target=run_flask).start()
    asyncio.run(run_bot())
