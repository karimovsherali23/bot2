import os
import asyncio
import io
import random
import string
import qrcode
import gspread
import logging
from flask import Flask, redirect, render_template_string
from oauth2client.service_account import ServiceAccountCredentials
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, ReplyKeyboardMarkup, KeyboardButton
from threading import Thread

# --- SOZLAMALAR ---
API_TOKEN = '8110490890:AAHTd6WduBLqjqD2lHfT62x1XnaELBQfjuY'
ADMIN_ID = 7693087447 
SHEET_NAME = "QR_Biznes" # Google Sheets faylingiz nomi aynan shunday bo'lishi shart!

# Render bergan tekin domen
BASE_URL = "https://bot2-l6hj.onrender.com" 

app = Flask(__name__)

def get_sheet():
    """Google Sheets bazasiga ulanish (Xavfsiz usul)"""
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    # Birinchi Render Secret Files'dan, keyin GitHub'dan qidiradi
    if os.path.exists("/etc/secrets/creds.json"):
        creds_path = "/etc/secrets/creds.json"
    else:
        creds_path = "creds.json"
        
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
        client = gspread.authorize(creds)
        return client.open(SHEET_NAME).sheet1
    except Exception as e:
        logging.error(f"Sheet ulanish xatosi: {e}")
        raise e

# --- WEB REDIRECTOR ---
@app.route('/')
def home():
    return "QR Tizimi Serveri Ishlamoqda! 🚀"

@app.route('/go/<qr_id>')
def redirect_handler(qr_id):
    try:
        sheet = get_sheet()
        cell = sheet.find(qr_id)
        row_data = sheet.row_values(cell.row)
        target_link = row_data[2] if len(row_data) > 2 else ""

        if target_link and target_link.startswith("http"):
            scans = int(row_data[4] if len(row_data) > 4 else 0) + 1
            sheet.update_cell(cell.row, 5, scans)
            return redirect(target_link)
        else:
            return render_template_string("""
                <body style="background:#121212;color:white;text-align:center;font-family:sans-serif;padding-top:100px;">
                    <div style="border:1px solid #333; display:inline-block; padding:30px; border-radius:15px;">
                        <h1 style="color:#ffcc00;">⚠️ Aktiv emas</h1>
                        <p>Bu QR kod hali sozlanmagan.</p>
                        <a href="https://t.me/qredit_bot?start={{qr_id}}" 
                           style="background:#0088cc; color:white; padding:10px 20px; text-decoration:none; border-radius:5px;">
                           Botda sozlash (ID: {{qr_id}})
                        </a>
                    </div>
                </body>
            """, qr_id=qr_id)
    except:
        return "Xato: Bunday QR kod topilmadi.", 404

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
        try:
            sheet = get_sheet()
            cell = sheet.find(qr_id)
            row = sheet.row_values(cell.row)
            await state.update_data(qr_row=cell.row, qr_pass=row[1], qr_id=qr_id)
            await message.answer(f"🆔 Kod: {qr_id}\n\nParolni kiriting:")
            await state.set_state(QRStates.waiting_for_password)
        except Exception as e:
            await message.answer(f"Xato: Ma'lumot topilmadi yoki Sheet xatosi: {e}")
    else:
        if message.from_user.id == ADMIN_ID:
            kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="➕ QR Yaratish")]], resize_keyboard=True)
            await message.answer("Xush kelibsiz Admin!", reply_markup=kb)

@dp.message(F.text == "➕ QR Yaratish")
async def admin_gen(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        qr_id = f"ID{random.randint(1000, 9999)}"
        password = ''.join(random.choices(string.digits, k=4))
        try:
            sheet = get_sheet()
            sheet.append_row([qr_id, password, "", "", 0])
            qr_url = f"{BASE_URL}/go/{qr_id}"
            qr = qrcode.make(qr_url)
            buf = io.BytesIO()
            qr.save(buf)
            photo = BufferedInputFile(buf.getvalue(), filename=f"{qr_id}.png")
            await message.answer_photo(photo, caption=f"✅ QR yaratildi!\n🔗 Link: {qr_url}\n🔑 Parol: {password}")
        except Exception as e:
            await message.answer(f"Sheetga yozishda xato: {e}")

@dp.message(QRStates.waiting_for_password)
async def process_password(message: types.Message, state: FSMContext):
    data = await state.get_data()
    if message.text == data['qr_pass']:
        await message.answer("To'g'ri! Endi linkni yuboring:")
        await state.set_state(QRStates.waiting_for_link)
    else:
        await message.answer("Xato parol!")

@dp.message(QRStates.waiting_for_link)
async def process_link(message: types.Message, state: FSMContext):
    link = message.text if message.text.startswith("http") else f"https://{message.text}"
    data = await state.get_data()
    try:
        sheet = get_sheet()
        sheet.update_cell(data['qr_row'], 3, link)
        await message.answer(f"Muvaffaqiyatli saqlandi! ✅")
        await state.clear()
    except Exception as e:
        await message.answer(f"Saqlashda xato: {e}")

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

async def run_bot():
    await dp.start_polling(bot)

if __name__ == "__main__":
    Thread(target=run_flask).start()
    asyncio.run(run_bot())
