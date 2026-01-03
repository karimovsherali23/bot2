import os
import asyncio
import io
import random
import string
import qrcode
import psycopg2
from psycopg2 import extras
import logging
from datetime import datetime
import matplotlib.pyplot as plt
import pandas as pd
from flask import Flask, redirect, render_template_string
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from threading import Thread

# --- SOZLAMALAR ---
API_TOKEN = '8110490890:AAFfTWofzUgGOzXxuw5K7nmNOXhusapstOg'
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
    # Asosiy jadval
    cur.execute('''
        CREATE TABLE IF NOT EXISTS qrcodes (
            qr_id TEXT PRIMARY KEY,
            password TEXT,
            target_link TEXT,
            owner_id BIGINT
        )
    ''')
    # Skanerlar tarixi jadvali
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
@app.route('/go/<qr_id>')
def redirect_handler(qr_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT target_link FROM qrcodes WHERE qr_id = %s", (qr_id,))
    data = cur.fetchone()
    if data:
        target_link = data[0]
        # Skanerlash vaqtini saqlash
        cur.execute("INSERT INTO scan_logs (qr_id) VALUES (%s)", (qr_id,))
        conn.commit()
        if target_link and target_link.startswith("http"):
            cur.close()
            conn.close()
            return redirect(target_link)
        
        bot_link = f"https://t.me/QRedit_bot?start={qr_id}"
        return render_template_string(f'<script>window.location.href="{bot_link}";</script>')
    return "❌ Xato", 404

# --- BOT QISMI ---
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

class QRStates(StatesGroup):
    waiting_for_password = State()
    waiting_for_new_link = State()

# --- GRAFIK YASASH FUNKSIYASI ---
def generate_stats_graph(qr_id):
    conn = get_db_connection()
    query = "SELECT scan_time FROM scan_logs WHERE qr_id = %s"
    df = pd.read_sql(query, conn, params=(qr_id,))
    conn.close()

    if df.empty:
        return None

    # Soatbay guruhlash
    df['hour'] = df['scan_time'].dt.hour
    stats = df['hour'].value_counts().sort_index()

    plt.figure(figsize=(10, 5))
    plt.bar(stats.index.astype(str), stats.values, color='skyblue')
    plt.title(f"QR ID: {qr_id} - Skanerlash vaqtlari (Soatbay)")
    plt.xlabel("Kun soati (0-23)")
    plt.ylabel("Skanerlar soni")
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()
    return buf

# --- BOT HANDLERS ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    args = message.text.split()[1:]
    if args:
        qr_id = args[0]
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT owner_id, password FROM qrcodes WHERE qr_id = %s", (qr_id,))
        res = cur.fetchone()
        
        if res:
            owner_id, password = res
            await state.update_data(qr_id=qr_id, correct_password=password)
            if owner_id is None or owner_id == message.from_user.id:
                await message.answer(f"🔒 QR ID: {qr_id}\nDavom etish uchun parolni kiriting:")
                await state.set_state(QRStates.waiting_for_password)
            else:
                await message.answer("❌ Bu QR kod boshqa foydalanuvchiga tegishli.")
        cur.close()
        conn.close()
    else:
        kb = ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="📊 Mening QR kodlarim")],
            [KeyboardButton(text="➕ Yangi QR yaratish (Admin)")] if message.from_user.id == ADMIN_ID else []
        ], resize_keyboard=True)
        await message.answer("Xush kelibsiz!", reply_markup=kb)

@dp.message(QRStates.waiting_for_password)
async def check_password(message: types.Message, state: FSMContext):
    data = await state.get_data()
    if message.text == data['correct_password']:
        qr_id = data['qr_id']
        # Egallash (agar birinchi marta bo'lsa)
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE qrcodes SET owner_id = %s WHERE qr_id = %s", (message.from_user.id, qr_id))
        conn.commit()
        cur.close()
        conn.close()
        
        await message.answer("✅ Parol to'g'ri! Endi yangi linkni yuboring:")
        await state.set_state(QRStates.waiting_for_new_link)
    else:
        await message.answer("❌ Xato parol. Qayta urinib ko'ring:")

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
    
    await message.answer(f"🎉 Saqlandi! Link: {link}")
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
            count = cur.fetchone()[0]
            
            text = f"🆔 ID: `{row['qr_id']}`\n🔗 Link: {row['target_link']}\n👁 Umumiy skanerlar: {count}"
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📈 Grafik Statistika", callback_data=f"graph_{row['qr_id']}")],
                [InlineKeyboardButton(text="✏️ Tahrirlash", callback_data=f"edit_start_{row['qr_id']}")]
            ])
            await message.answer(text, reply_markup=kb, parse_mode="Markdown")
    cur.close()
    conn.close()

@dp.callback_query(F.data.startswith("graph_"))
async def show_graph(callback: types.CallbackQuery):
    qr_id = callback.data.split("_")[1]
    graph_buf = generate_stats_graph(qr_id)
    
    if graph_buf:
        photo = BufferedInputFile(graph_buf.read(), filename="stats.png")
        await callback.message.answer_photo(photo, caption=f"📊 {qr_id} uchun soatbay statistika")
    else:
        await callback.answer("Hali ma'lumotlar yetarli emas.", show_alert=True)

@dp.callback_query(F.data.startswith("edit_start_"))
async def edit_start(callback: types.CallbackQuery, state: FSMContext):
    qr_id = callback.data.split("_")[2]
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT password FROM qrcodes WHERE qr_id = %s", (qr_id,))
    pwd = cur.fetchone()[0]
    cur.close()
    conn.close()
    
    await state.update_data(qr_id=qr_id, correct_password=pwd)
    await callback.message.answer("Xavfsizlik uchun parolni kiriting:")
    await state.set_state(QRStates.waiting_for_password)
    await callback.answer()

@dp.message(F.text == "➕ Yangi QR yaratish (Admin)")
async def admin_gen(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        qr_id = f"ID{random.randint(1000, 9999)}"
        password = ''.join(random.choices(string.digits, k=4))
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO qrcodes (qr_id, password, target_link) VALUES (%s, %s, %s)", (qr_id, password, ""))
        conn.commit()
        cur.close()
        conn.close()
        
        qr_url = f"{BASE_URL}/go/{qr_id}"
        qr = qrcode.make(qr_url)
        buf = io.BytesIO()
        qr.save(buf)
        photo = BufferedInputFile(buf.getvalue(), filename=f"{qr_id}.png")
        await message.answer_photo(photo, caption=f"✅ Yaratildi!\n🆔 {qr_id}\n🔑 Parol: {password}")

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

async def run_bot():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    Thread(target=run_flask).start()
    asyncio.run(run_bot())
