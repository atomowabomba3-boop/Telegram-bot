import asyncio
import logging
import sqlite3
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, ChatMemberUpdated

TOKEN = "8795322916:AAHg7sfezoa-xTYk1Dp1xRW8xBwJnY1FAts"
CHANNEL_ID = "@undergroundzon"

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

def init_db():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    # Tabela użytkowników i losów
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            tickets INTEGER DEFAULT 1,
            invited_by INTEGER
        )
    """)
    # Tabela unikalnych linków zaproszeniowych do kanału
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS invite_links (
            invite_link TEXT PRIMARY KEY,
            user_id INTEGER
        )
    """)
    # Tabela zakupionych e-booków
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
        BotCommand(command="help", description="Show available commands"),
    ]
    await bot.set_my_commands(commands)

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    tickets = get_or_create_user(user_id)
    
    welcome_text = (
        "👋 Welcome to the Ticket & E-book System!\n\n"
        "You can check your tickets, get your channel invite link, or check your e-books.\n\n"
        f"Your current ticket balance: {tickets}\n\n"
        "Use /help to see all commands."
    )
    await message.answer(welcome_text)

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    help_text = (
        "🤖 **Available Commands:**\n\n"
        "📊 /tickets - Check your ticket balance\n"
        "🔗 /ref - Get your channel invite link\n"
        "📚 /ebooks - View your purchased e-books\n"
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
            f"🔗 **Your personal channel invite link:**\n{link}\n\n"
            "Share this link with your friends! When they join the channel using it, you will automatically get a ticket.",
            parse_mode="Markdown"
        )
    except Exception as e:
        await message.answer("⚠️ Error generating link. Make sure the bot is an administrator on the channel.")
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
        await message.answer("📚 You don't have any e-books yet. Check out our channel to purchase some!")
    else:
        ebooks_list = "\n".join([f"• {ebook[0]}" for ebook in ebooks])
        await message.answer(f"📚 **Your purchased e-books:**\n\n{ebooks_list}", parse_mode="Markdown")

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
                                f"🎉 Someone joined the channel using your invite link!\n"
                                f"Your new ticket balance: {inviter_tickets}"
                            )
                        except Exception:
                            pass

            get_or_create_user(new_user_id)
            try:
                await bot.send_message(
                    new_user_id,
                    "👋 Welcome to the channel! You have received your starting ticket."
                )
            except Exception:
                pass

@dp.message(Command("reset_contest"))
async def cmd_reset_contest(message: types.Message):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET tickets = 0")
    conn.commit()
    conn.close()
    
    await message.answer("🔄 New contest started! All user tickets have been reset.")

async def main():
    logging.basicConfig(level=logging.INFO)
    await set_bot_commands(bot)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
