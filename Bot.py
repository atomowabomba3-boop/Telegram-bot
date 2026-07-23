import asyncio
import logging
import sqlite3
import os
import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, ChatMemberUpdated, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile

TOKEN = "8795322916:AAHg7sfezoa-xTYk1Dp1xRW8xBwJnY1FAts"
CRYPTO_PAY_TOKEN = "612964:AAtkz79Sjrh5hks8knampljxXpnzRpS94Hz"
CHAT_ID = "@Undrgroundzone"
TOPIC_ID = 2

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

TIERS = {
    "buy_tier1": {"name": "Ebook Tier 1", "price": 2.0, "tickets": 50, "file": "ebook_1.pdf"},
    "buy_tier2": {"name": "Ebook Tier 2", "price": 5.0, "tickets": 200, "file": "ebook_2.pdf"},
    "buy_tier3": {"name": "Ebook Tier 3", "price": 10.0, "tickets": 500, "file": "ebook_3.pdf"},
    "buy_ebook1": {"name": "Single Ebook #1", "price": 1.5, "tickets": 20, "file": "single_1.pdf"},
    "buy_ebook2": {"name": "Single Ebook #2", "price": 1.5, "tickets": 20, "file": "single_2.pdf"}
}

async def create_crypto_invoice(amount: float, asset: str, description: str, payload: str):
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
        BotCommand(command="store", description="Show available e-books"),
        BotCommand(command="tickets", description="Check your tickets"),
        BotCommand(command="ref", description="Get your invite link"),
        BotCommand(command="ebooks", description="Your purchased e-books"),
        BotCommand(command="post_ebooks", description="Post store to group"),
        BotCommand(command="sim_pay", description="Simulate a successful purchase"),
        BotCommand(command="help", description="Show help"),
    ]
    await bot.set_my_commands(commands)

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    args = message.text.split()
    
    if len(args) > 1:
        payload = args[1]
        parts = payload.split("_")
        
        if len(parts) == 3:
            tier_key = f"{parts[0]}_{parts[1]}"
            asset = parts[2].upper()
            
            if tier_key in TIERS:
                tier_data = TIERS[tier_key]
                try:
                    invoice_url = await create_crypto_invoice(
                        amount=tier_data["price"],
                        asset=asset,
                        description=f"Purchase: {tier_data['name']} + {tier_data['tickets']} tickets",
                        payload=payload
                    )
                    
                    pay_keyboard = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text=f"💳 PAY WITH {asset}", url=invoice_url)]
                    ])
                    
                    await message.answer(
                        f"🛒 **Generating payment for {tier_data['name']}**\n\n"
                        f"🎟 **Included:** {tier_data['tickets']} tickets\n"
                        f"💰 **Amount:** ${tier_data['price']} USD equivalent in {asset}\n\n"
                        "Click the button below to complete your payment via CryptoBot:",
                        reply_markup=pay_keyboard,
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    await message.answer("⚠️ An error occurred while generating payment. Please try again later.")
                    logging.error(f"CryptoPay error: {e}")
                return
        
        if payload in TIERS:
            select_keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="USDT", callback_data=f"pay_{payload}_USDT"),
                    InlineKeyboardButton(text="BTC", callback_data=f"pay_{payload}_BTC"),
                    InlineKeyboardButton(text="ETH", callback_data=f"pay_{payload}_ETH")
                ]
            ])
            await message.answer(
                f"💱 **Choose cryptocurrency for {TIERS[payload]['name']} (${TIERS[payload]['price']}):**",
                reply_markup=select_keyboard,
                parse_mode="Markdown"
            )
            return

    tickets = get_or_create_user(user_id)
    welcome_text = (
        "👋 Welcome to the Undrgroundzone System!\n\n"
        "Here you can check your tickets, invite link, and buy e-books.\n\n"
        f"Your ticket balance: {tickets}\n\n"
        "Use /store to see available e-books."
    )
    await message.answer(welcome_text)

@dp.callback_query(lambda c: c.data and c.data.startswith("pay_"))
async def process_currency_choice(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    tier_key = f"{parts[1]}_{parts[2]}"
    asset = parts[3].upper()
    
    if tier_key in TIERS:
        tier_data = TIERS[tier_key]
        try:
            invoice_url = await create_crypto_invoice(
                amount=tier_data["price"],
                asset=asset,
                description=f"Purchase: {tier_data['name']} + {tier_data['tickets']} tickets",
                payload=f"{tier_key}_{asset}"
            )
            
            pay_keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"💳 PAY {tier_data['price']} {asset}", url=invoice_url)]
            ])
            
            await callback.message.edit_text(
                f"🛒 **Invoice ready for {tier_data['name']}**\n\n"
                f"💰 **Amount:** {tier_data['price']} {asset}\n\n"
                "Click the button below to pay:",
                reply_markup=pay_keyboard,
                parse_mode="Markdown"
            )
        except Exception as e:
            await callback.message.answer("⚠️ Error generating invoice. Try again later.")
            logging.error(f"CryptoPay error: {e}")
            
    await callback.answer()

@dp.message(Command("store"))
async def cmd_store(message: types.Message):
    store_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟢 Ebook Tier 1 ($2)", callback_data="sel_buy_tier1")],
        [InlineKeyboardButton(text="🔵 Ebook Tier 2 ($5)", callback_data="sel_buy_tier2")],
        [InlineKeyboardButton(text="🟣 Ebook Tier 3 ($10)", callback_data="sel_buy_tier3")],
        [InlineKeyboardButton(text="📖 Single Ebook #1 ($1.5)", callback_data="sel_buy_ebook1")],
        [InlineKeyboardButton(text="📖 Single Ebook #2 ($1.5)", callback_data="sel_buy_ebook2")]
    ])
    await message.answer("📚 **Available E-books Store:**\nSelect a product to purchase:", reply_markup=store_keyboard, parse_mode="Markdown")

@dp.callback_query(lambda c: c.data and c.data.startswith("sel_"))
async def process_store_selection(callback: types.CallbackQuery):
    payload = callback.data.replace("sel_", "")
    if payload in TIERS:
        select_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="USDT", callback_data=f"pay_{payload}_USDT"),
                InlineKeyboardButton(text="BTC", callback_data=f"pay_{payload}_BTC"),
                InlineKeyboardButton(text="ETH", callback_data=f"pay_{payload}_ETH")
            ]
        ])
        await callback.message.edit_text(
            f"💱 **Choose cryptocurrency for {TIERS[payload]['name']} (${TIERS[payload]['price']}):**",
            reply_markup=select_keyboard,
            parse_mode="Markdown"
        )
    await callback.answer()

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    help_text = (
        "🤖 **Available Commands:**\n\n"
        "📚 /store - Browse and buy e-books\n"
        "📊 /tickets - Check your ticket balance\n"
        "🔗 /ref - Get your invite link\n"
        "📖 /ebooks - View your purchased e-books\n"
        "🛒 /post_ebooks - Post store to group\n"
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
        invite = await bot.create_chat_invite_link(chat_id=CHAT_ID, creates_join_request=False)
        link = invite.invite_link
        
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO invite_links (invite_link, user_id) VALUES (?, ?)", (link, user_id))
        conn.commit()
        conn.close()
        
        await message.answer(
            f"🔗 **Your personal invite link:**\n{link}\n\n"
            "Share this link with your friends to earn tickets!",
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
        await message.answer("📚 You don't have any e-books yet. Use /store to check them out!")
    else:
        ebooks_list = "\n".join([f"• {ebook[0]}" for ebook in ebooks])
        await message.answer(f"📚 **Your purchased e-books:**\n\n{ebooks_list}", parse_mode="Markdown")

@dp.message(Command("sim_pay"))
async def cmd_sim_pay(message: types.Message):
    user_id = message.from_user.id
    tier_key = "buy_tier3"
    tier_data = TIERS[tier_key]
    
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET tickets = tickets + ? WHERE user_id = ?", (tier_data["tickets"], user_id))
    cursor.execute("INSERT INTO user_ebooks (user_id, ebook_name) VALUES (?, ?)", (user_id, tier_data["name"]))
    conn.commit()
    
    cursor.execute("SELECT tickets FROM users WHERE user_id = ?", (user_id,))
    total_tickets = cursor.fetchone()[0]
    conn.close()
    
    await message.answer(
        f"🧪 **[PURCHASE SIMULATION]**\n\n"
        f"✅ Successfully simulated payment for: **{tier_data['name']}**\n"
        f"🎟 Added tickets: **+{tier_data['tickets']}**\n"
        f"📊 Your new ticket balance: **{total_tickets}**",
        parse_mode="Markdown"
    )
    
    file_to_send = tier_data["file"]
    if os.path.exists(file_to_send):
        await message.answer_document(
            document=FSInputFile(file_to_send),
            caption=f"🎁 Here is your purchased file: {tier_data['name']}"
        )
    else:
        await message.answer(f"⚠️ Warning: Database updated, but file `{file_to_send}` was not found on the server.")

@dp.message(Command("post_ebooks"))
async def cmd_post_ebooks(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟢 Ebook Tier 1 ($2)", callback_data="sel_buy_tier1")],
        [InlineKeyboardButton(text="🔵 Ebook Tier 2 ($5)", callback_data="sel_buy_tier2")],
        [InlineKeyboardButton(text="🟣 Ebook Tier 3 ($10)", callback_data="sel_buy_tier3")],
        [InlineKeyboardButton(text="📖 Single Ebook #1 ($1.5)", callback_data="sel_buy_ebook1")],
        [InlineKeyboardButton(text="📖 Single Ebook #2 ($1.5)", callback_data="sel_buy_ebook2")]
    ])
    
    try:
        await bot.send_message(
            chat_id=CHAT_ID,
            message_thread_id=TOPIC_ID,
            text="📚 **Undrgroundzone E-book Store**\n\nChoose an e-book or package below:",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
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
                        inviter_tickets = cursor.fetchone()[0]
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
