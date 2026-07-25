import asyncio
import os

from aiogram import Bot, Dispatcher
from dotenv import load_dotenv


load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(TOKEN)
dp = Dispatcher()


async def main():
    print("🚀 UndergroundZone started")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
