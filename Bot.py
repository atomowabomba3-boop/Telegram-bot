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
        await message.answer(f"Witaj! Zostałeś zaproszony przez użytkownika o ID: {ref_id}. Otrzymujesz swój los startowy!")
    else:
        await message.answer("Witaj w systemie losów i e-booków! Użyj /losy, aby sprawdzić swój bilans.")

@dp.message(Command("losy"))
async def cmd_losy(message: types.Message):
    await message.answer("Twój aktualny bilans:\n- Losy stałe: 1\n- Losy z zaproszeń: 0\n- Losy z zakupów: 0")

async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
