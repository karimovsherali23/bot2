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
BASE_URL = "https://bot2-l6hj.onrender.com" 

app = Flask(__name__)

def get_sheet():
    """Google Sheets bazasiga lug'at orqali ulanish (JWT xatosini yo'qotadi)"""
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    # DIQQAT: private_key qismidagi \n belgilarini o'chirib yubormang!
    creds_dict = {
  "type": "service_account",
  "project_id": "telegrambotsheetsintegratsiya",
  "private_key_id": "2ffc82339c89bcf04c08be1bab729702f0b5ae66",
  "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvAIBADANBgkqhkiG9w0BAQEFAASCBKYwggSiAgEAAoIBAQDlTdKHX/bHJBGS\nHiKk9w9WSVbV3C1nJTZTK5xZTH5xJmiATlIxteH1zNwM0CCdQDqFiQozqe2plFBN\nEzRhJzZWc998g19e86jH8E8Jk6AbN997pkNK2IP+tgn4192qZ6hR4zQVZSF81hbx\n6UhabXlKbBohjnc9sNUu7/QPVvSgrOAwj67MZ4HxwHFPOtrzxKCUBl71rLBYE8mG\nR+wqUL7tIYBLCnP9c2budgLXeLrOrD7KvV3zcbbe6zc3XReIee211oWrB4FFalO2\nohsvrYRvfsfh42gD4Xkhg5qnEEwiaa40oP0kJ/4WBvrgtJ4y5SKxc9K3OLNxi6Fv\nnZoI+wD9AgMBAAECggEAEn4GcLLxRqmWvisufZHMG5gSB/C3+6XBXg86DmyQFOV1\nT4WhdM9Xf/hrtZ/SRYRAw/SjjTuSxlaG7FRUaNJd/DZfi13X4uMxFSDA6wOMCa3l\nmMX1jtNrv66kGryj7IJsDWCOmnwbqYLlelBnLJ3ABpu1tseTv7ajVqP00YjgdRWc\n6u0A47i47SUU4YqjYFIVEIIbA98em4n1tj1mTEIt7IIhVxiqmhLZ/+QyHNHfZX7q\nveqfIN5WR72JefbbMqx2YnGP5LJZ7Ch3UJMKw2DU0YCMQ1y/DFAYq4cHntRgMYqz\nHK7PvXbGG1XHDIHB0q2MyGpNcmewwH8MoPsbn460KQKBgQD7YVT8oLcUohrrFXuf\n1dXflrPob4dSm08AHCKMK/XmfZT7MmUqr7mZnt27tAxnX8IKR4Uve2TsW7qURgi6\nI3Oz6NvnBrWlg7itZxhGCEwDlf4LxFgoD55TqXJdAkX+xVP2SZRhSilfjgkiPoYG\n1opem3chKeWpfC9pFGHoBkBHqQKBgQDphKDk6+Fp3c7QujM9ozt+yMjH03sQU++z\nnt0qiTlUnkml9jHaJFOoV4qFjFyohMfstpfame7fy/BKOxg5CpwGiPbfrggVZVSg\n2PXRZ2KoAbMezzvFAcHMCWqJ7Rs9IROza1NOTZy/3+XNk4DCniyPK6VxCVPnNUtP\nRw9YtamzNQKBgELhFldP+uWGa1r4EDfqEEi4M403fu0/XLlOwvJAD+AOsUBTnA7L\nSbnRRnTV5ibqlxldBdYoIiWwEee46kF7hSDsZvUEF/e9H7kioJahRnf9w+Uli768\nyQbBIigUnsK1hS0VTmDD9lXx2ARAVjAjjBS3j+5G009QNtziC1pLr3ZhAoGAXR91\n5jSmzMgWjKhkfMUWmcXKQ93zKpy+b1wACNF2WmdRKWzXjo2ECxL1+7Hw1Yc2DxD1\n18ghOYAjkAam70Bq3jRKdwL42Edziz1aMirPbf5XhwbPaA3+UbbDlMNIZIVHTPqU\n2xoaU24fP27+Hx5i2KloLX6xxfc71B6bYR340a0CgYAqA4jj4+DPsQ0vanGxSA6S\ndXkTOghqCYKF5tEWpjFYgECa19v6Z9yX9GzeFFCWM583ZWs71uSx+O1frzb+ongd\n/+esV0CjATUYwSOcDIP4etUvO/4LINVhOrSGj9WD4qTm98/hNWvgptYbzfOOlWuD\nnSsmlRT0ZnfNufskTq/U9Q==\n-----END PRIVATE KEY-----\n",
  "client_email": "telegram-bot@telegrambotsheetsintegratsiya.iam.gserviceaccount.com",
  "client_id": "102910072290711163990",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/telegram-bot%40telegrambotsheetsintegratsiya.iam.gserviceaccount.com",
  "universe_domain": "googleapis.com"
}

    
    try:
        # Fayldan emas, bevosita lug'atdan (dict) o'qiymiz
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        return client.open(SHEET_NAME).sheet1
    except Exception as e:
        logging.error(f"Google Sheets ulanish xatosi: {e}")
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
                    <h1 style="color:#ffcc00;">⚠️ Aktiv emas</h1>
                    <p>Bu QR kod hali sozlanmagan.</p>
                </body>
            """)
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
            await message.answer(f"Xato: {e}")
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
            await message.answer(f"Xato: {e}")

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
        await message.answer(f"Xato: {e}")

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

async def run_bot():
    # Conflict xatosini oldini olish uchun avvalgi sessiyani yopamiz
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    Thread(target=run_flask).start()
    asyncio.run(run_bot())
