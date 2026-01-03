import os
import asyncio
import io
import random
import string
import qrcode
import sqlite3
import logging
from flask import Flask, redirect, render_template_string
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, ReplyKeyboardMarkup, KeyboardButton
from threading import Thread

# --- SOZLAMALAR ---
# Tokenni yangilagan bo'lsangiz, yangisini qo'ying
API_TOKEN = '8231142795:AAE5Z2mnf_TJP31pT9SaeIkfiVAaZWApxlc'
# O'zingizning ID raqamingizni @userinfobot orqali tekshirib yozing
ADMIN_ID = 7693087447 
BASE_URL = "https://bot2-l6hj.onrender.com" 

app = Flask(__name__)

# --- BAZA BILAN ISHLASH (SQLITE) ---
def init_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS qrcodes (
            qr_id TEXT PRIMARY KEY,
            password TEXT,
            target_link TEXT,
            scans INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def update_db(qr_id, password=None, link=None, increment_scans=False):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    if link:
        cursor.execute("UPDATE qrcodes SET target_link = ? WHERE qr_id = ?", (link, qr_id))
    elif increment_scans:
        cursor.execute("UPDATE qrcodes SET scans = scans + 1 WHERE qr_id = ?", (qr_id,))
    else:
        cursor.execute("INSERT OR REPLACE INTO qrcodes (qr_id, password, target_link, scans) VALUES (?, ?, ?, ?)", 
                       (qr_id, password, "", 0))
    conn.commit()
    conn.close()

def get_qr_data(qr_id):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM qrcodes WHERE qr_id = ?", (qr_id,))
    data = cursor.fetchone()
    conn.close()
    return data

# --- WEB REDIRECTOR ---
@app.route('/')
def home():
    return "🚀 QR Tizimi Serveri Ishlamoqda!"

@app.route('/go/<qr_id>')
def redirect_handler(qr_id):
    data = get_qr_data(qr_id)
    if data:
        target_link = data[2]
        if target_link and target_link.startswith("http"):
            update_db(qr_id, increment_scans=True)
            return redirect(target_link)
        
        # Link yo'q bo'lsa, botga yo'naltirish tugmasi
        bot_link = f"https://t.me/QRedit_bot?start={qr_id}"
        return render_template_string(f"""
            <body style="background:#121212;color:white;text-align:center;font-family:sans-serif;padding-top:100px;">
                <h1 style="color:#ffcc00;">⚠️ QR Sozlanmagan</h1>
                <p>Ushbu QR kodga link biriktirish uchun quyidagi tugmani bosing:</p>
                <br>
                <a href="{bot_link}" 
                   style="display:inline-block;padding:15px 30px;background:#0088cc;color:white;text-decoration:none;border-radius:50px;font-weight:bold;">
                   ⚙️ Botda sozlash
                </a>
            </body>
        """)
    return "❌ Topilmadi.", 404

# --- BOT QISMI ---
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
            await message.answer(f"🆔 QR-ID: {qr_id}\n\nUshbu QR kodni sozlash uchun parolni kiriting:")
            await state.set_state(QRStates.waiting_for_password)
        else:
            await message.answer("❌ Xato: Bunday QR kod bazada mavjud emas.")
    elif message.from_user.id == ADMIN_ID:
        kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="➕ QR Yaratish")]], resize_keyboard=True)
        await message.answer("Salom Admin! Yangi QR kod yaratish uchun tugmani bosing.", reply_markup=kb)
    else:
        await message.answer("Xush kelibsiz! Ushbu bot QR kodlarni boshqarish uchun ishlatiladi.")

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
        
        await message.answer_photo(
            photo, 
            caption=f"✅ Yangi QR kod yaratildi!\n\n🔗 Link: {qr_url}\n🔑 Parol: {password}\n\nSkaner qiling va sozlang!"
        )

@dp.message(QRStates.waiting_for_password)
async def process_password(message: types.Message, state: FSMContext):
    data = await state.get_data()
    if message.text == data['qr_pass']:
        await message.answer("✅ Parol to'g'ri! Endi QR kod skaner qilinganda ochilishi kerak bo'lgan linkni yuboring (masalan: instagram.com/profil):")
        await state.set_state(QRStates.waiting_for_link)
    else:
        await message.answer("❌ Xato parol! Qayta urinib ko'ring:")

@dp.message(QRStates.waiting_for_link)
async def process_link(message: types.Message, state: FSMContext):
    link = message.text if message.text.startswith("http") else f"https://{message.text}"
    data = await state.get_data()
    update_db(data['qr_id'], link=link)
    await message.answer(f"🎉 Muvaffaqiyatli saqlandi!\n\nEndi ushbu QR kod foydalanuvchini mana bu yerga yuboradi:\n{link}")
    await state.clear()

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

async def run_bot():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    Thread(target=run_flask).start()
    asyncio.run(run_bot())
