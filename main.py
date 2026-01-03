import os
import asyncio
import io
import random
import string
import qrcode
import psycopg2
import logging
from flask import Flask, redirect, render_template_string
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, ReplyKeyboardMarkup, KeyboardButton
from threading import Thread

# --- SOZLAMALAR ---
API_TOKEN = '8231142795:AAERQML-EPpxJ1GRyd2u4eQAd6R6Ek1iYzM'
ADMIN_ID = 7693087447 
BASE_URL = "https://bot2-l6hj.onrender.com" 

# Skrinshotingizdagi "External Database URL" ni shu yerga qo'ydim
DB_URL = "postgresql://qr_baza_user:TiEUOA70TG53kF9nvUecCWAGH938wSdN@dpg-d5cosder433s739v350g-a.oregon-postgres.render.com/qr_baza"

app = Flask(__name__)

# --- BAZA BILAN ISHLASH (POSTGRESQL) ---
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
            scans INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    cur.close()
    conn.close()

init_db()

def update_db(qr_id, password=None, link=None, increment_scans=False):
    conn = get_db_connection()
    cur = conn.cursor()
    if link:
        cur.execute("UPDATE qrcodes SET target_link = %s WHERE qr_id = %s", (link, qr_id))
    elif increment_scans:
        cur.execute("UPDATE qrcodes SET scans = scans + 1 WHERE qr_id = %s", (qr_id,))
    else:
        cur.execute("INSERT INTO qrcodes (qr_id, password, target_link, scans) VALUES (%s, %s, %s, %s) ON CONFLICT (qr_id) DO NOTHING", 
                       (qr_id, password, "", 0))
    conn.commit()
    cur.close()
    conn.close()

def get_qr_data(qr_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM qrcodes WHERE qr_id = %s", (qr_id,))
    data = cur.fetchone()
    cur.close()
    conn.close()
    return data

# --- WEB SERVER VA BOT MANTIG'I (AVVALGI BILAN BIR XIL) ---
@app.route('/')
def home():
    return "🚀 QR Tizimi (PostgreSQL) Ishlamoqda!"

@app.route('/go/<qr_id>')
def redirect_handler(qr_id):
    data = get_qr_data(qr_id)
    if data:
        target_link = data[2]
        if target_link and target_link.startswith("http"):
            update_db(qr_id, increment_scans=True)
            return redirect(target_link)
        
        bot_link = f"https://t.me/QRedit_bot?start={qr_id}"
        return render_template_string(f"""
            <body style="background:#121212;color:white;text-align:center;font-family:sans-serif;padding-top:100px;">
                <h1 style="color:#ffcc00;">⚠️ QR Sozlanmagan</h1>
                <p>Ushbu QR kodni sozlash uchun botga o'ting:</p>
                <br>
                <a href="{bot_link}" style="display:inline-block;padding:15px 30px;background:#0088cc;color:white;text-decoration:none;border-radius:50px;font-weight:bold;">⚙️ Botda sozlash</a>
            </body>
        """)
    return "❌ QR kod topilmadi.", 404

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

class QRStates(StatesGroup):
    waiting_for_password = State()
    waiting_for_link = State()

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    args = message.text.split()[1:]
    if args:
        qr_id = args[0]
        data = get_qr_data(qr_id)
        if data:
            await state.update_data(qr_id=qr_id, qr_pass=data[1])
            await message.answer(f"🆔 QR-ID: {qr_id}\n\nParolni kiriting:")
            await state.set_state(QRStates.waiting_for_password)
        else:
            await message.answer("❌ Xato: ID topilmadi.")
    elif message.from_user.id == ADMIN_ID:
        kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="➕ QR Yaratish")]], resize_keyboard=True)
        await message.answer("Salom Admin!", reply_markup=kb)

@dp.message(F.text == "➕ QR Yaratish")
async def admin_gen(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        qr_id = f"ID{random.randint(1000, 9999)}"
        password = ''.join(random.choices(string.digits, k=4))
        update_db(qr_id, password)
        qr_url = f"{BASE_URL}/go/{qr_id}"
        qr = qrcode.make(qr_url)
        buf = io.BytesIO()
        qr.save(buf)
        photo = BufferedInputFile(buf.getvalue(), filename=f"{qr_id}.png")
        await message.answer_photo(photo, caption=f"✅ QR yaratildi!\n🔗 {qr_url}\n🔑 Parol: {password}")

@dp.message(QRStates.waiting_for_password)
async def process_password(message: types.Message, state: FSMContext):
    data = await state.get_data()
    if message.text == data['qr_pass']:
        await message.answer("✅ To'g'ri! Linkni yuboring:")
        await state.set_state(QRStates.waiting_for_link)
    else:
        await message.answer("❌ Xato parol!")

@dp.message(QRStates.waiting_for_link)
async def process_link(message: types.Message, state: FSMContext):
    link = message.text if message.text.startswith("http") else f"https://{message.text}"
    data = await state.get_data()
    update_db(data['qr_id'], link=link)
    await message.answer(f"✅ Saqlandi!")
    await state.clear()

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

async def run_bot():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    Thread(target=run_flask).start()
    asyncio.run(run_bot())
