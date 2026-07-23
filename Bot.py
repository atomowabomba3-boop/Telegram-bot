import asyncio
import logging
import sqlite3
import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, ChatMemberUpdated, InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = "8795322916:AAHg7sfezoa-xTYk1Dp1xRW8xBwJnY1FAts"
CRYPTO_PAY_TOKEN = "612964:AAtkz79Sjrh5hks8knampljxXpnzRpS94Hz"
CHAT_ID = "@Undrgroundzone"
TOPIC_ID = 2

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

async def create_crypto_invoice(amount: float, asset: str, description: str, payload: str):
    """Directly communicates with CryptoBot HTTP API supporting multiple assets (USDT, BTC, ETH, etc.)."""
    url = "https://pay.crypt.bot/api/createInvoice"
    headers = {"Crypto-Pay-API-Token": CRYPTO_PAY_TOKEN}
    data = {
        "asset": asset,
        "amount": str(amount),
        "description": description,
        "payload": payload,
        "allow_comments": False,
        "allow_anonymous": False
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=data) as response:
            result = await response.json()
            if result.get("ok"):
                return result["result"]["bot_invoice_url"]
            else:
                logging.error(f"CryptoBot API Error: {result}")
                raise Exception("Failed to create invoice via CryptoBot")

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
        BotCommand(command="tickets", description="Check your tickets"),
        BotCommand(command="ref", description="Get your invite link"),
        BotCommand(command="ebooks", description="Your purchased e-books"),
        BotCommand(command="post_ebooks", description="Post store to group topic"),
        BotCommand(command="sim_pay", description="Simulate a successful purchase"),
        BotCommand(command="help", description="Show help"),
    ]
    await bot.set_my_commands(commands)

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    args = message.text.split()
    
    if len(args) > 1:
        payload = args[1] # Format expected: buy_tier1_USDT, buy_tier1_BTC, buy_tier1_ETH
        parts = payload.split("_")
        
        if len(parts) == 3:
            tier_key, asset = f"{parts[0]}_{parts[1]}", parts[2].upper()
            tiers = {
                "buy_tier1": {"name": "Ebook Tier 1", "price": 2.0, "tickets": 50},
                "buy_tier2": {"name": "Ebook Tier 2", "price": 5.0, "tickets": 200},
                "buy_tier3": {"name": "Ebook Tier 3", "price": 10.0, "tickets": 500}
            }
            
            if tier_key in tiers:
                tier_data = tiers[tier_key]
                try:
                    invoice_url = await create_crypto_invoice(
                        amount=tier_data["price"],
                        asset=asset,
                        description=f"Purchase: {tier_data['name']} + {tier_data['tickets']} tickets in Undrgroundzone",
                        payload=payload
                    )
                    
                    pay_keyboard = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text=f"💳 PAY WITH {asset}", url=invoice_url)]
                    ])
                    
                    await message.answer(
                        f"🛒 **Generating payment for {tier_data['name']}**\n\n"
                        f"🎟 **Included:** {tier_data['tickets']} tickets\n"
                        f"💰 **Amount:** ${tier_data['price']} USD equivalent in {asset}\n\n"
                        "Click the button below to complete your payment:",
                        reply_markup=pay_keyboard,
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    await message.answer("⚠️ An error occurred while generating payment. Please try again later.")
                    logging.error(f"CryptoPay error: {e}")
                return
        
        # If user clicked a tier button directly without asset choice, show asset selection menu
        base_tiers = {
            "buy_tier1": "Ebook Tier 1 ($2)",
            "buy_tier2": "Ebook Tier 2 ($5)",
            "buy_tier3": "Ebook Tier 3 ($10)"
        }
        if payload in base_tiers:
            select_keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="USDT", url=f"https://t.me/{message.bot.username}?start={payload}_USDT"),
                    InlineKeyboardButton(text="BTC", url=f"https://t.me/{message.bot.username}?start={payload}_BTC"),
                    InlineKeyboardButton(text="ETH", url=f"https://t.me/{message.bot.username}?start={payload}_ETH")
                ]
            ])
            await message.answer(
                f"💱 **Choose cryptocurrency for {base_tiers[payload]}:**",
                reply_markup=select_keyboard,
                parse_mode="Markdown"
            )
            return

    tickets = get_or_create_user(user_id)
    welcome_text = (
        "👋 Welcome to the Undrgroundzone System!\n\n"
        "Here you can check your tickets, invite link, and claim your e-books.\n\n"
        f"Your ticket balance: {tickets}\n\n"
        "Use /help to see available commands."
    )
    await message.answer(welcome_text)

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    help_text = (
        "🤖 **Available Commands:**\n\n"
        "📊 /tickets - Check your ticket balance\n"
        "🔗 /ref - Get your invite link\n"
        "📚 /ebooks - View your purchased e-books\n"
        "🛒 /post_ebooks - Post store to group topic\n"
        "🧪 /sim_pay - Simulate a test purchase\n"
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
            chat_id=CHAT_ID,
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
            "Share this link with your friends! When someone joins using it, you will automatically receive a ticket.",
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
        await message.answer("📚 You don't have any e-books yet. Check out the store in our group!")
    else:
        ebooks_list = "\n".join([f"• {ebook[0]}" for ebook in ebooks])
        await message.answer(f"📚 **Your purchased e-books:**\n\n{ebooks_list}", parse_mode="Markdown")

@dp.message(Command("sim_pay"))
async def cmd_sim_pay(message: types.Message):
    user_id = message.from_user.id
    tier_name = "Ebook Tier 3"
    added_tickets = 500
    
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET tickets = tickets + ? WHERE user_id = ?", (added_tickets, user_id))
    cursor.execute("INSERT INTO user_ebooks (user_id, ebook_name) VALUES (?, ?)", (user_id, tier_name))
    conn.commit()
    
    cursor.execute("SELECT tickets FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    total_tickets = row[0] if row else added_tickets
    conn.close()
    
    await message.answer(
        f"🧪 **[PURCHASE SIMULATION]**\n\n"
        f"✅ Successfully simulated payment for: **{tier_name}**\n"
        f"🎟 Added tickets: **+{added_tickets}**\n"
        f"📊 Your new ticket balance: **{total_tickets}**\n\n"
        f"Check /ebooks and /tickets commands!",
        parse_mode="Markdown"
    )

@dp.message(Command("post_ebooks"))
async def cmd_post_ebooks(message: types.Message):
    photo_green = "ebook_green.png.jpg"
    photo_blue = "ebook_blue.png.jpg"
    photo_purple = "ebook_purple.png.jpg"

    bot_info = await bot.get_me()
    bot_username = bot_info.username

    caption_1 = (
        "🟢 **Ebook Tier 1**\n"
        "Basic package for beginners.\n\n"
        "🎟 **Included:** 50 tickets\n"
        "💰 **Price:** $2 USD"
    )
    keyboard_1 = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 BUY TIER 1 ($2)", url=f"https://t.me/{bot_username}?start=buy_tier1")]
    ])

    caption_2 = (
        "🔵 **Ebook Tier 2**\n"
        "Medium package with advanced materials.\n\n"
        "🎟 **Included:** 200 tickets\n"
        "💰 **Price:** $5 USD"
    )
    keyboard_2 = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 BUY TIER 2 ($5)", url=f"https://t.me/{bot_username}?start=buy_tier2")]
    ])

    caption_3 = (
        "🟣 **Ebook Tier 3**\n"
        "Elite package – full access and maximum perks.\n\n"
        "🎟 **Included:** 500 tickets\n"
        "💰 **Price:** $10 USD"
    )
    keyboard_3 = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 BUY TIER 3 ($10)", url=f"https://t.me/{bot_username}?start=buy_tier3")]
    ])

    try:
        await bot.send_photo(chat_id=CHAT_ID, message_thread_id=TOPIC_ID, photo=types.FSInputFile(photo_green), caption=caption_1, reply_markup=keyboard_1, parse_mode="Markdown")
        await bot.send_photo(chat_id=CHAT_ID, message_thread_id=TOPIC_ID, photo=types.FSInputFile(photo_blue), caption=caption_2, reply_markup=keyboard_2, parse_mode="Markdown")
        await bot.send_photo(chat_id=CHAT_ID, message_thread_id=TOPIC_ID, photo=types.FSInputFile(photo_purple), caption=caption_3, reply_markup=keyboard_3, parse_mode="Markdown")
        await message.answer("✅ Store successfully posted to the group topic!")
    except Exception as e:
        await message.answer(f"⚠️ Error posting store: {e}")

@dp.chat_member()
async def member_join(event: ChatMemberUpdated):
    if event.chat.username and f"@{event.chat.username.lower()}" == CHAT_ID.lower():
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
                                f"🎉 Someone joined the group using your invite link!\n"
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
