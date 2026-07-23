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
TOPIC_ID = 3

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

TIERS = {
    "tier1": {
        "name": "Ebook Tier 1", 
        "price": 2.0, 
        "tickets": 50, 
        "file": "ebook_1.pdf",
        "photo": "ebook_green.png.jpg",
        "payload": "buy_tier1"
    },
    "tier2": {
        "name": "Ebook Tier 2", 
        "price": 5.0, 
        "tickets": 200, 
        "file": "ebook_2.pdf",
        "photo": "ebook_blue.png.jpg",
        "payload": "buy_tier2"
    },
    "tier3": {
        "name": "Ebook Tier 3", 
        "price": 10.0, 
        "tickets": 500, 
        "file": "ebook_3.pdf",
        "photo": "ebook_purple.png.jpg",
        "payload": "buy_tier3"
    }
}

async def create_crypto_invoice(amount: float, asset: str, description: str, payload: str):
    url = "https://pay.crypt.bot/api/createInvoice"
    headers = {"Crypto-Pay-API-Token": CRYPTO_PAY_TOKEN}
    data = {
        "amount": str(amount),
        "currency_type": "fiat",
        "fiat": "USD",
        "accepted_assets": asset,
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
        BotCommand(command="sim_pay", description="Simulate purchase (e.g. /sim_pay tier1)"),
        BotCommand(command="tier1", description="Simulate purchase of Tier 1"),
        BotCommand(command="tier2", description="Simulate purchase of Tier 2"),
        BotCommand(command="tier3", description="Simulate purchase of Tier 3"),
        BotCommand(command="help", description="Show help"),
    ]
    await bot.set_my_commands(commands)

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    get_or_create_user(user_id)
    args = message.text.split()
    
    if len(args) > 1:
        payload = args[1]
        parts = payload.split("_")
        
        if len(parts) == 3:
            tier_key = f"{parts[1]}"
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
                        [InlineKeyboardButton(text=f"💳 PAY ${tier_data['price']} IN {asset}", url=invoice_url)]
                    ])
                    
                    await message.answer(
                        f"🛒 **Generating payment for {tier_data['name']}**\n\n"
                        f"🎟 **Included:** {tier_data['tickets']} tickets\n"
                        f"💰 **Amount:** ${tier_data['price']} USD (equivalent in {asset})\n\n"
                        "Click the button below to complete your payment:",
                        reply_markup=pay_keyboard,
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    await message.answer("⚠️ An error occurred while generating payment. Please try again later.")
                    logging.error(f"CryptoPay error: {e}")
                return
        
        clean_payload = payload.replace("buy_", "")
        if clean_payload in TIERS:
            bot_username = (await bot.get_me()).username
            p_key = f"buy_{clean_payload}"
            select_keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="USDT", url=f"https://t.me/{bot_username}?start={p_key}_USDT"),
                    InlineKeyboardButton(text="TON", url=f"https://t.me/{bot_username}?start={p_key}_TON"),
                    InlineKeyboardButton(text="BTC", url=f"https://t.me/{bot_username}?start={p_key}_BTC")
                ],
                [
                    InlineKeyboardButton(text="ETH", url=f"https://t.me/{bot_username}?start={p_key}_ETH"),
                    InlineKeyboardButton(text="LTC", url=f"https://t.me/{bot_username}?start={p_key}_LTC"),
                    InlineKeyboardButton(text="TRX", url=f"https://t.me/{bot_username}?start={p_key}_TRX")
                ]
            ])
            await message.answer(
                f"💱 **Choose cryptocurrency for {TIERS[clean_payload]['name']} (${TIERS[clean_payload]['price']}):**",
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
        "🧪 /sim_pay <tier1/tier2/tier3> - Simulate a test purchase\n"
        "⚡ /tier1, /tier2, /tier3 - Quick simulate test purchase for specific tier\n"
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

async def process_simulation(message: types.Message, tier_key: str):
    user_id = message.from_user.id
    get_or_create_user(user_id)
    
    if tier_key not in TIERS:
        await message.answer("⚠️ Invalid tier!", parse_mode="Markdown")
        return
        
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
            caption=f"🎁 Here is your purchased file for {tier_data['name']}!"
        )
    else:
        await message.answer(f"⚠️ Note: Database updated, but file `{file_to_send}` was not found in the bot directory.")

@dp.message(Command("sim_pay"))
async def cmd_sim_pay(message: types.Message):
    args = message.text.split()
    tier_choice = args[1].lower().replace("buy_", "") if len(args) > 1 else "tier3"
    await process_simulation(message, tier_choice)

@dp.message(Command("tier1"))
async def cmd_tier1(message: types.Message):
    await process_simulation(message, "tier1")

@dp.message(Command("tier2"))
async def cmd_tier2(message: types.Message):
    await process_simulation(message, "tier2")

@dp.message(Command("tier3"))
async def cmd_tier3(message: types.Message):
    await process_simulation(message, "tier3")

@dp.message(Command("post_ebooks"))
async def cmd_post_ebooks(message: types.Message):
    bot_username = (await bot.get_me()).username

    for tier_key, data in TIERS.items():
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"🛒 BUY {data['name'].upper()} (${data['price']})", url=f"https://t.me/{bot_username}?start={data['payload']}")]
        ])
        
        caption_text = (
            f"📚 **{data['name']}**\n\n"
            f"💰 Price: **${data['price']} USD**\n"
            f"🎟 Tickets included: **{data['tickets']}**\n\n"
            "Click the button below to purchase:"
        )

        try:
            if os.path.exists(data["photo"]):
                await bot.send_photo(
                    chat_id=CHAT_ID,
                    message_thread_id=TOPIC_ID,
                    photo=FSInputFile(data["photo"]),
                    caption=caption_text,
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
            else:
                await bot.send_message(
                    chat_id=CHAT_ID,
                    message_thread_id=TOPIC_ID,
                    text=f"⚠️ [Image `{data['photo']}` missing]\n\n" + caption_text,
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
        except Exception as e:
            await message.answer(f"⚠️ Error posting {data['name']}: {e}")
            return

    await message.answer("✅ Store successfully posted to the group topic with individual images!")

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
