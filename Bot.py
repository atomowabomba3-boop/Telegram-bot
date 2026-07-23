import asyncio
import logging
import sqlite3
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.storage.memory import MemoryStorage

TOKEN = "8795322916:AAHg7sfezoa-xTYk1Dp1xRW8xBwJnY1FAts"

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Inicjalizacja bazy danych SQLite do trzymania losów użytkowników
def init_db():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            tickets INTEGER DEFAULT 1,
            invited_by INTEGER
        )
    """)
    conn.commit()
    conn.close()

init_db()

# Funkcja pomocnicza do pobierania/tworzenia użytkownika
def get_or_create_user(user_id: int, ref_id: int = None):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT tickets FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    
    if not row:
        cursor.execute("INSERT INTO users (user_id, tickets, invited_by) VALUES (?, 1, ?)", (user_id, ref_id))
        conn.commit()
        tickets = 1
    else:
        tickets = row[0]
        
    conn.close()
    return tickets

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    args = message.text.split(maxsplit=1)
    user_id = message.from_user.id
    
    ref_id = None
    if len(args) > 1:
        try:
            ref_id = int(args[1])
            if ref_id == user_id:
                ref_id = None # Nie można zaprosić samego siebie
        except ValueError:
            pass
            
    tickets = get_or_create_user(user_id, ref_id)
    
    if ref_id:
        await message.answer(f"Welcome! You were invited. Your starting ticket balance: {tickets}")
    else:
        await message.answer(f"Welcome to the ticket and e-book system! Your current ticket balance: {tickets}")

@dp.message(Command("tickets"))
async def cmd_tickets(message: types.Message):
    user_id = message.from_user.id
    tickets = get_or_create_user(user_id)
    await message.answer(f"Your current ticket balance:\n- Total tickets: {tickets}")

# Komenda do resetowania losów przy nowym konkursie (np. /reset_contest)
@dp.message(Command("reset_contest"))
async def cmd_reset_contest(message: types.Message):
    # Tutaj możesz ewentualnie dodać zabezpieczenie, żeby tylko Ty (Admin ID) mogłeś to wpisać
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    # Resetuje losy wszystkich użytkowników z powrotem do wartości bazowej (np. 0 lub 1)
    cursor.execute("UPDATE users SET tickets = 0")
    conn.commit()
    conn.close()
    
    await message.answer("🔄 New contest started! All user tickets have been reset.")

async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
