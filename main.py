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
import cv2  # pyzbar o'rniga opencv ishlatamiz
from flask import Flask, redirect, render_template_string
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from threading import Thread

# --- SOZLAMALAR ---
API_TOKEN = '8110490890:AAHT7WrEHMe9XEoxd2WoniH9WlaIhR0YUNY'
ADMIN_ID = 7693087447 
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

# --- WEB SERVER (REDIRECTOR) ---
@app.route('/')
def home(): return "QR Server Active"

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
    return "❌ QR Topilmadi", 404

# --- BOT QISMI ---
logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

class QRStates(StatesGroup):
    waiting_for_password = State()
    waiting_for_new_link = State()

# --- GRAFIK GENERATSIYASI ---
def generate_stats_graph(qr_id):
    conn = get_db_connection()
    df = pd.read_sql(f"SELECT scan_time FROM scan_logs WHERE qr_id = '{qr_id}'", conn)
    conn.close()
    if df.empty: return None

    df['hour'] = pd.to_datetime(df['scan_time']).dt.hour
    stats = df['hour'].value_counts().sort_index()
    plt.figure(figsize=(10, 5))
    stats.plot(kind='bar', color='orange')
    plt.title(f"QR ID: {qr_id} - Faollik (Soatbay)")
    plt.xlabel("Kun soati")
    plt.ylabel("Skanerlar soni")
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()
    return buf

# --- ADMIN UCHUN QR SKANER (OpenCV ishlatilgan) ---
@dp.message(F.photo & (F.from_user.id == ADMIN_ID))
async def admin_photo_scan(message: types.Message):
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    file_data = await bot.download_file(file.file_path)
    
    try:
        # Rasmni OpenCV o'qiydigan formatga o'tkazish
        file_bytes = np.asarray(bytearray(file_data.read()), dtype=np.uint8)
        img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        
        # QR kodni aniqlash
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
                    await message.answer(f"🔍 **QR Topildi:**\n🆔 ID: `{res['qr_id']}`\n🔑 Parol: `{res['password']}`\n👤 Egasi: `{res['owner_id'] or 'Yoq'}`\n🔗 Link: {res['target_link'] or 'Yoq'}", parse_mode="Markdown")
                else:
                    await message.answer(f"❌ ID: `{qr_id}` bazada yo'q.")
            else:
                await message.answer(f"ℹ️ Bu begona QR kod: `{data}`")
        else:
            await message.answer("❌ Rasmda QR kod aniqlanmadi.")
    except Exception as e:
        logging.error(f"Scan error: {e}")
        await message.answer("⚠️ QR tahlil qilishda xatolik.")

# --- ASOSIY HANDLERLAR (AVVALGI BILAN BIR XIL) ---
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

@dp.callback_query(F.data.startswith("gr_"))
async def show_gr(callback: types.CallbackQuery):
    qr_id = callback.data.split("_")[1]
    buf = generate_stats_graph(qr_id)
    if buf:
        await callback.message.answer_photo(BufferedInputFile(buf.read(), filename="st.png"), caption=f"📊 {qr_id} faolligi")
    else:
        await callback.answer("Ma'lumot yetarli emas.")

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
    await callback.message.answer("Parolni kiriting:")
    await state.set_state(QRStates.waiting_for_password)
    await callback.answer()

@dp.message(F.text == "➕ Yangi QR yaratish (Admin)")
async def admin_gen(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        qr_id = f"ID{random.randint(1000, 9999)}"
        pwd = ''.join(random.choices(string.digits, k=4))
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO qrcodes (qr_id, password, target_link) VALUES (%s, %s, %s)", (qr_id, pwd, ""))
        conn.commit()
        cur.close()
        conn.close()
        qr_url = f"{BASE_URL}/go/{qr_id}"
        img = qrcode.make(qr_url)
        buf = io.BytesIO()
        img.save(buf)
        await message.answer_photo(BufferedInputFile(buf.getvalue(), filename="qr.png"), caption=f"✅ Yaratildi!\n🆔 `{qr_id}`\n🔑 Parol: `{pwd}`", parse_mode="Markdown")

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

async def run_bot():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    Thread(target=run_flask).start()
    asyncio.run(run_bot())
