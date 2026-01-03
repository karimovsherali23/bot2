import os
import asyncio
import io
import random
import string
import qrcode
import psycopg2
from psycopg2 import extras
import logging
from flask import Flask, redirect, render_template_string
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from threading import Thread

# --- SOZLAMALAR ---
API_TOKEN = '8110490890:AAEovTgj07x1gnR5ylBryvl2mF1IvwUieMs'
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
    # owner_id ustuni foydalanuvchini aniqlash uchun qo'shildi
    cur.execute('''
        CREATE TABLE IF NOT EXISTS qrcodes (
            qr_id TEXT PRIMARY KEY,
            password TEXT,
            target_link TEXT,
            scans INTEGER DEFAULT 0,
            owner_id BIGINT
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
        if target_link and target_link.startswith("http"):
            cur.execute("UPDATE qrcodes SET scans = scans + 1 WHERE qr_id = %s", (qr_id,))
            conn.commit()
            cur.close()
            conn.close()
            return redirect(target_link)
        
        bot_link = f"https://t.me/QRedit_bot?start={qr_id}"
        return render_template_string(f'<script>window.location.href="{bot_link}";</script>')
    return "❌ Xato", 404

# --- BOT QISMI ---
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

class EditStates(StatesGroup):
    waiting_for_new_link = State()

# --- KLAVIATURALAR ---
def main_menu(user_id):
    buttons = [[KeyboardButton(text="📊 Mening QR kodlarim")]]
    if user_id == ADMIN_ID:
        buttons.append([KeyboardButton(text="➕ Yangi QR yaratish (Admin)")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

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
            if owner_id is None:
                # QR kod hali hech kimga tegishli emas, ulaymiz
                cur.execute("UPDATE qrcodes SET owner_id = %s WHERE qr_id = %s", (message.from_user.id, qr_id))
                conn.commit()
                await message.answer(f"✅ Ushbu QR kod ({qr_id}) profilingizga biriktirildi!\nEndi linkni yuboring:")
                await state.update_data(qr_id=qr_id)
                await state.set_state(EditStates.waiting_for_new_link)
            elif owner_id == message.from_user.id:
                await message.answer("Siz ushbu QR kod egasisiz. Yangi link yuboring:")
                await state.update_data(qr_id=qr_id)
                await state.set_state(EditStates.waiting_for_new_link)
            else:
                await message.answer("❌ Bu QR kod boshqa foydalanuvchiga tegishli.")
        cur.close()
        conn.close()
    else:
        await message.answer("Xush kelibsiz!", reply_markup=main_menu(message.from_user.id))

@dp.message(F.text == "📊 Mening QR kodlarim")
async def my_qrs(message: types.Message):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=extras.DictCursor)
    cur.execute("SELECT * FROM qrcodes WHERE owner_id = %s", (message.from_user.id,))
    rows = cur.fetchall()
    
    if not rows:
        await message.answer("Sizda hali biriktirilgan QR kodlar yo'q.")
    else:
        for row in rows:
            text = (f"🆔 **ID:** `{row['qr_id']}`\n"
                    f"🔗 **Link:** {row['target_link'] or 'Sozlanmagan'}\n"
                    f"👁 **Skanerlar soni:** {row['scans']}\n"
                    f"🔑 **Parol:** `{row['password']}`")
            
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="✏️ Tahrirlash", callback_data=f"edit_{row['qr_id']}"),
                InlineKeyboardButton(text="🖼 QR yuklash", callback_data=f"getqr_{row['qr_id']}")
            ]])
            await message.answer(text, reply_markup=kb, parse_mode="Markdown")
    cur.close()
    conn.close()

@dp.callback_query(F.data.startswith("edit_"))
async def edit_callback(callback: types.CallbackQuery, state: FSMContext):
    qr_id = callback.data.split("_")[1]
    await state.update_data(qr_id=qr_id)
    await callback.message.answer(f"🆔 {qr_id} uchun yangi linkni yuboring:")
    await state.set_state(EditStates.waiting_for_new_link)
    await callback.answer()

@dp.message(EditStates.waiting_for_new_link)
async def process_new_link(message: types.Message, state: FSMContext):
    new_link = message.text if message.text.startswith("http") else f"https://{message.text}"
    data = await state.get_data()
    qr_id = data['qr_id']
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE qrcodes SET target_link = %s WHERE qr_id = %s", (new_link, qr_id))
    conn.commit()
    cur.close()
    conn.close()
    
    await message.answer("✅ Muvaffaqiyatli saqlandi!", reply_markup=main_menu(message.from_user.id))
    await state.clear()

@dp.message(F.text == "➕ Yangi QR yaratish (Admin)")
async def admin_gen(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        qr_id = f"ID{random.randint(1000, 9999)}"
        password = ''.join(random.choices(string.digits, k=4))
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO qrcodes (qr_id, password, target_link, scans) VALUES (%s, %s, %s, %s)", 
                   (qr_id, password, "", 0))
        conn.commit()
        cur.close()
        conn.close()
        
        qr_url = f"{BASE_URL}/go/{qr_id}"
        qr = qrcode.make(qr_url)
        buf = io.BytesIO()
        qr.save(buf)
        photo = BufferedInputFile(buf.getvalue(), filename=f"{qr_id}.png")
        await message.answer_photo(photo, caption=f"✅ Yangi bo'sh QR yaratildi!\n🆔 ID: {qr_id}\n🔑 Parol: {password}")

# --- ISHGA TUSHIRISH ---
def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

async def run_bot():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    Thread(target=run_flask).start()
    asyncio.run(run_bot())
