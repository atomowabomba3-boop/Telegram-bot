import asyncio
import logging
import sqlite3
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, ChatMemberUpdated, InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = "8795322916:AAHg7sfezoa-xTYk1Dp1xRW8xBwJnY1FAts"
CHANNEL_ID = "@Undrgroundzone"

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

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
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS invite_links (
            invite_link TEXT PRIMARY KEY,
            user_id INTEGER
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_ebooks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            ebook_name TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

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

async def set_bot_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="Start the bot"),
        BotCommand(command="tickets", description="Check your ticket balance"),
        BotCommand(command="ref", description="Get your channel invite link"),
        BotCommand(command="ebooks", description="View your purchased e-books"),
        BotCommand(command="post_ebooks", description="Post ebooks store to group"),
        BotCommand(command="help", description="Show available commands"),
    ]
    await bot.set_my_commands(commands)

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    tickets = get_or_create_user(user_id)
    
    welcome_text = (
        "👋 Welcome to the Ticket & E-book System!\n\n"
        "You can check your tickets, get your invite link, or check your e-books.\n\n"
        f"Your current ticket balance: {tickets}\n\n"
        "Use /help to see all commands."
    )
    await message.answer(welcome_text)

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    help_text = (
        "🤖 **Available Commands:**\n\n"
        "📊 /tickets - Check your ticket balance\n"
        "🔗 /ref - Get your invite link\n"
        "📚 /ebooks - View your purchased e-books\n"
        "🛒 /post_ebooks - Send ebooks to group\n"
        "❓ /help - Show help"
    )
    await message.answer(help_text, parse_mode="Markdown")

@dp.message(Command("tickets"))
async def cmd_tickets(message: types.Message):
    user_id = message.from_user.id
    tickets = get_or_create_user(user_id)
    await message.answer(f"Your current ticket balance:\n- Total tickets: {tickets}")

@dp.message(Command("ref"))
async def cmd_ref(message: types.Message):
    user_id = message.from_user.id
    get_or_create_user(user_id)
    
    try:
        invite = await bot.create_chat_invite_link(
            chat_id=CHANNEL_ID,
            creates_join_request=False
        )
        link = invite.invite_link
        
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO invite_links (invite_link, user_id) VALUES (?, ?)", (link, user_id))
        conn.commit()
        conn.close()
        
        await message.answer(
            f"🔗 **Your personal invite link:**\n{link}\n\n"
            "Share this link! When someone joins using it, you will automatically get a ticket.",
            parse_mode="Markdown"
        )
    except Exception as e:
        await message.answer("⚠️ Error generating link. Make sure the bot is an administrator in the group.")
        logging.error(f"Invite link error: {e}")

@dp.message(Command("ebooks"))
async def cmd_ebooks(message: types.Message):
    user_id = message.from_user.id
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT ebook_name FROM user_ebooks WHERE user_id = ?", (user_id,))
    ebooks = cursor.fetchall()
    conn.close()
    
    if not ebooks:
        await message.answer("📚 You don't have any e-books yet. Check out our group shop to purchase some!")
    else:
        ebooks_list = "\n".join([f"• {ebook[0]}" for ebook in ebooks])
        await message.answer(f"📚 **Your purchased e-books:**\n\n{ebooks_list}", parse_mode="Markdown")

@dp.message(Command("post_ebooks"))
async def cmd_post_ebooks(message: types.Message):
    photo_green = "ebook_green.png"
    photo_blue = "ebook_blue.png"
    photo_purple = "ebook_purple.png"

    caption_1 = (
        "🟢 **Underground Start (Pakiet Podstawowy)**\n"
        "Idealny wybór na start. Solidne fundamenty i instrukcje krok po kroku.\n\n"
        "💰 **Cena:** $2 USD"
    )
    keyboard_1 = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 KUP ZA $2", url="https://t.me/Undrgroundzone_bot?start=buy_green_2")]
    ])

    caption_2 = (
        "🔵 **Underground Pro (Pakiet Średni)**\n"
        "Zaawansowane techniki, triki i optymalizacja działań.\n\n"
        "💰 **Cena:** $5 USD"
    )
    keyboard_2 = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 KUP ZA $5", url="https://t.me/Undrgroundzone_bot?start=buy_blue_5")]
    ])

    caption_3 = (
        "🟣 **Underground Master (Pakiet Elitarny)**\n"
        "Kompleksowy zestaw, ukryte dodatki i pełny pakiet losów.\n\n"
        "💰 **Cena:** $10 USD"
    )
    keyboard_3 = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 KUP ZA $10", url="https://t.me/Undrgroundzone_bot?start=buy_purple_10")]
    ])

    try:
        await bot.send_photo(chat_id=CHANNEL_ID, photo=types.FSInputFile(photo_green), caption=caption_1, reply_markup=keyboard_1, parse_mode="Markdown")
        await bot.send_photo(chat_id=CHANNEL_ID, photo=types.FSInputFile(photo_blue), caption=caption_2, reply_markup=keyboard_2, parse_mode="Markdown")
        await bot.send_photo(chat_id=CHANNEL_ID, photo=types.FSInputFile(photo_purple), caption=caption_3, reply_markup=keyboard_3, parse_mode="Markdown")
        await message.answer("✅ E-books post successfully sent to the group!")
    except Exception as e:
        await message.answer(f"⚠️ Error sending photos: {e}")

@dp.chat_member()
async def member_join(event: ChatMemberUpdated):
    if event.chat.username and f"@{event.chat.username.lower()}" == CHANNEL_ID.lower():
        if event.new_chat_member.status == "member" and event.old_chat_member.status in ["left", "kicked"]:
            new_user_id = event.new_chat_member.user.id
            invite_link_obj = event.invite_link
            
            if invite_link_obj and invite_link_obj.invite_link:
                link_url = invite_link_obj.invite_link
                
                conn = sqlite3.connect("bot_database.db")
                cursor = conn.cursor()
                cursor.execute("SELECT user_id FROM invite_links WHERE invite_link = ?", (link_url,))
                row = cursor.fetchone()
                conn.close()
                
                if row:
                    inviter_id = row[0]
                    if inviter_id != new_user_id:
                        conn = sqlite3.connect("bot_database.db")
                        cursor = conn.cursor()
                        cursor.execute("UPDATE users SET tickets = tickets + 1 WHERE user_id = ?", (inviter_id,))
                        conn.commit()
                        
                        cursor.execute("SELECT tickets FROM users WHERE user_id = ?", (inviter_id,))
                        res = cursor.fetchone()
                        inviter_tickets = res[0] if res else 0
                        conn.close()
                        
                        try:
                            await bot.send_message(
                                inviter_id,
                                f"🎉 Someone joined using your invite link!\n"
                                f"Your new ticket balance: {inviter_tickets}"
                            )
                        except Exception:
                            pass

            get_or_create_user(new_user_id)
            try:
                await bot.send_message(
                    new_user_id,
                    "👋 Welcome to the group! You have received your starting ticket."
                )
            except Exception:
                pass

async def main():
    logging.basicConfig(level=logging.INFO)
    await set_bot_commands(bot)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
