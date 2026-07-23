import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.storage.memory import MemoryStorage

# Wklej tutaj token swojego głównego bota od BotFather
TOKEN = "8795322916:AAHg7sfezoa-xTYk1Dp1xRW8xBwJnY1FAts"

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    args = message.text.split(maxsplit=1)
    user_id = message.from_user.id
    
    if len(args) > 1:
        ref_id = args[1]
        await message.answer(f"Welcome! You were invited by user ID: {ref_id}. You received your starting ticket!")
    else:
        await message.answer("Welcome to the ticket and e-book system! Use /tickets to check your balance.")

@dp.message(Command("losy"))
async def cmd_losy(message: types.Message):
    # Tutaj w przyszłości podepnisz zmienną z całkowitą liczbą losów użytkownika
    total_tickets = 1  
    await message.answer(f"Your current ticket balance:\n- Total tickets: {total_tickets}")

async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
