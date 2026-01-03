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
SHEET_NAME = "QR_Biznes"

# !!! DIQQAT: Bu yerga o'z domeningizni yozasiz (masalan: https://sizningdomen.uz)
BASE_URL = "https://marsmobi-qr.onrender.com" 

app = Flask(__name__)

def get_sheet():
    """Google Sheets bazasiga ulanish"""
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name("creds.json", scope)
    client = gspread.authorize(creds)
    return client.open(SHEET_NAME).sheet1

# --- WEB REDIRECTOR (SAYT QISMI) ---
@app.route('/go/<qr_id>')
def redirect_handler(qr_id):
    """Skaner qilinganda linkni topib yo'naltiruvchi mantiq"""
    try:
        sheet = get_sheet()
        cell = sheet.find(qr_id)
        row_data = sheet.row_values(cell.row)
        
        # Foydalanuvchi linki (3-ustun)
        target_link = row_data[2] if len(row_data) > 2 else ""

        if target_link and target_link.startswith("http"):
            # Statistika: Skanerlar sonini oshirish (5-ustun)
            scans = int(row_data[4] if len(row_data) > 4 else 0) + 1
            sheet.update_cell(cell.row, 5, scans)
            
            # TO'G'RIDAN-TO'G'RI YO'NALTIRISH
            return redirect(target_link)
        else:
            # Aktivmas bo'lsa ko'rsatiladigan sahifa
            return render_template_string("""
                <body style="background:#121212;color:white;text-align:center;font-family:sans-serif;padding-top:100px;">
                    <div style="border:1px solid #333; display:inline-block; padding:30px; border-radius:15px;">
                        <h1 style="color:#ffcc00;">⚠️ Aktiv emas</h1>
                        <p>Bu futbolka egasi hali o'z linkini ulamagan.</p>
                        <a href="https://t.me/qredit_bot?start={{qr_id}}" 
                           style="background:#0088cc; color:white; padding:10px 20px; text-decoration:none; border-radius:5px;">
                           Bot orqali sozlash
                        </a>
                    </div>
                </body>
            """, qr_id=qr_id)
    except:
        return "QR kod topilmadi.", 404

# --- TELEGRAM BOT QISMI ---
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
            await message.answer(f"🆔 Kod: {qr_id}\n\nKiyimni aktivlashtirish uchun parolni kiriting:")
            await state.set_state(QRStates.waiting_for_password)
        except:
            await message.answer("Xato: Kod topilmadi.")
    else:
        if message.from_user.id == ADMIN_ID:
            kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="➕ QR Yaratish")]], resize_keyboard=True)
            await message.answer("Xush kelibsiz, Admin!", reply_markup=kb)
        else:
            await message.answer("Salom! QR kodni skanerlang.")

@dp.message(F.text == "➕ QR Yaratish")
async def admin_gen(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        qr_id = f"ID{random.randint(1000, 9999)}"
        password = ''.join(random.choices(string.digits, k=4))
        sheet = get_sheet()
        sheet.append_row([qr_id, password, "", "", 0])
        
        # QR ichida o'z domeningiz linki bo'ladi
        qr_url = f"{BASE_URL}/go/{qr_id}"
        qr = qrcode.make(qr_url)
        buf = io.BytesIO()
        qr.save(buf)
        photo = BufferedInputFile(buf.getvalue(), filename=f"{qr_id}.png")
        await message.answer_photo(photo, caption=f"✅ QR yaratildi!\n🆔: {qr_id}\n🔑: {password}\n🔗: {qr_url}")

@dp.message(QRStates.waiting_for_password)
async def process_password(message: types.Message, state: FSMContext):
    data = await state.get_data()
    if message.text == data['qr_pass']:
        await message.answer("To'g'ri! Skanerlanganda ochiladigan linkni yuboring:")
        await state.set_state(QRStates.waiting_for_link)
    else:
        await message.answer("Xato parol!")

@dp.message(QRStates.waiting_for_link)
async def process_link(message: types.Message, state: FSMContext):
    link = message.text if message.text.startswith("http") else f"https://{message.text}"
    data = await state.get_data()
    sheet = get_sheet()
    sheet.update_cell(data['qr_row'], 3, link)
    await message.answer(f"Muvaffaqiyatli! ✅\nEndi QR skanerlanganda to'g'ri shu manzil ochiladi:\n{link}")
    await state.clear()

# --- ISHGA TUSHIRISH ---
def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

async def run_bot():
    await dp.start_polling(bot)

if __name__ == "__main__":
    Thread(target=run_flask).start()
    asyncio.run(run_bot())