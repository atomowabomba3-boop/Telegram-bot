import asyncio
import logging
import sqlite3
import os
import random
import aiohttp
from aiohttp import web
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, ChatMemberUpdated, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, CallbackQuery

TOKEN = "8795322916:AAHg7sfezoa-xTYk1Dp1xRW8xBwJnY1FAts"
CRYPTO_PAY_TOKEN = "612964:AAtkz79Sjrh5hks8knampljxXpnzRpS94Hz"
CHAT_ID = "@Undrgroundzone"
TOPIC_ID = 2          # Temat dla giveawayów i wyników
STORE_TOPIC_ID = 3    # Temat dedykowany tylko na informacje o kupnie e-booków

ADMIN_IDS = [8998575936]

# Flaga zapobiegająca uruchomieniu dwóch losowań jednocześnie
is_drawing_in_progress = False

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

async def handle(request):
    return web.Response(text="Bot is running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

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
    conn = sqlite3.connect("bot_database.db", timeout=30.0)
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
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
        CREATE TABLE IF NOT EXISTS referral_history (
            inviter_id INTEGER,
            invited_id INTEGER,
            PRIMARY KEY (inviter_id, invited_id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_ebooks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            ebook_name TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS giveaway_pool (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            amount REAL DEFAULT 0.0
        )
    """)
    cursor.execute("""
        INSERT OR IGNORE INTO giveaway_pool (id, amount) VALUES (1, 0.0)
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS giveaway_participants (
            user_id INTEGER PRIMARY KEY
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS active_giveaways (
            message_id INTEGER PRIMARY KEY,
            winners_count INTEGER,
            ends_at TEXT,
            status TEXT DEFAULT 'active',
            winners_text TEXT,
            ended_at TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

def get_display_pool(raw_amount: float) -> float:
    return raw_amount if raw_amount >= 15.0 else 15.0

def get_or_create_user(user_id: int, ref_id: int = None):
    conn = sqlite3.connect("bot_database.db", timeout=30.0)
    cursor = conn.cursor()
    cursor.execute("SELECT tickets FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    
    if not row:
        cursor.execute("INSERT OR IGNORE INTO users (user_id, tickets, invited_by) VALUES (?, 1, ?)", (user_id, ref_id))
        conn.commit()
        tickets = 1
    else:
        tickets = row[0]
        
    conn.close()
    return tickets

def add_to_giveaway_pool_raw(amount: float):
    conn = sqlite3.connect("bot_database.db", timeout=30.0)
    cursor = conn.cursor()
    cursor.execute("UPDATE giveaway_pool SET amount = amount + ? WHERE id = 1", (amount,))
    conn.commit()
    cursor.execute("SELECT amount FROM giveaway_pool WHERE id = 1")
    current_pool = cursor.fetchone()[0]
    conn.close()
    return current_pool

async def update_all_active_giveaways(bot: Bot):
    conn = sqlite3.connect("bot_database.db", timeout=30.0)
    cursor = conn.cursor()
    cursor.execute("SELECT amount FROM giveaway_pool WHERE id = 1")
    raw_pool_amount = cursor.fetchone()[0]
    pool_amount = get_display_pool(raw_pool_amount)
    
    cursor.execute("SELECT COUNT(*) FROM giveaway_participants")
    participants_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT message_id, winners_count, ends_at FROM active_giveaways WHERE status = 'active'")
    giveaways = cursor.fetchall()
    conn.close()

    now = datetime.now()
    for msg_id, winners_count, ends_at_str in giveaways:
        ends_at = datetime.fromisoformat(ends_at_str)
        remaining = ends_at - now
        
        if remaining.total_seconds() <= 0:
            await finish_giveaway_automatically(bot, msg_id, winners_count)
            continue
            
        hours, remainder = divmod(int(remaining.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        time_left = f"{hours}h {minutes}m {seconds}s"

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎉 JOIN GIVEAWAY", callback_data="join_giveaway")]
        ])
        text = (
            "🎁 **UNDRGROUNDZONE MEGA GIVEAWAY** 🎁\n\n"
            f"💰 **Current Prize Pool:** `${pool_amount:.2f} USD`\n"
            f"🏆 **Winners Count:** `{winners_count}` (prize split equally)\n"
            f"👥 **Participants:** `{participants_count}` people\n"
            f"⏳ **Ends in:** `{time_left}`\n\n"
            "💡 *Chcesz zwiększyć swoje szanse? Kupuj e-booki w sklepie lub zapraszaj znajomych za pomocą komendy /ref! Każdy bilet to większa szansa na wygraną.*\n\n"
            "Click the button below to participate!"
        )
        try:
            await bot.edit_message_text(
                chat_id=CHAT_ID,
                message_id=msg_id,
                text=text,
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
        except Exception:
            pass

async def finish_giveaway_automatically(bot: Bot, msg_id: int, winners_count: int):
    global is_drawing_in_progress
    
    conn = sqlite3.connect("bot_database.db", timeout=30.0)
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM active_giveaways WHERE message_id = ?", (msg_id,))
    row = cursor.fetchone()
    
    if not row or row[0] != 'active':
        conn.close()
        return

    cursor.execute("SELECT amount FROM giveaway_pool WHERE id = 1")
    raw_pool_amount = cursor.fetchone()[0]
    pool_amount = get_display_pool(raw_pool_amount)

    cursor.execute("SELECT user_id FROM giveaway_participants")
    participants = [row[0] for row in cursor.fetchall()]

    ended_at_str = datetime.now().isoformat()

    if not participants:
        cursor.execute("UPDATE active_giveaways SET status = 'ended', winners_text = ?, ended_at = ? WHERE message_id = ?", ("Nobody participated", ended_at_str, msg_id))
        cursor.execute("DELETE FROM giveaway_participants")
        conn.commit()
        conn.close()
        try:
            await bot.edit_message_text(
                chat_id=CHAT_ID,
                message_id=msg_id,
                text="🎉 **UNDRGROUNDZONE GIVEAWAY RESULTS** 🎉\n\n⚠️ Nobody participated in the giveaway!",
                parse_mode="Markdown"
            )
        except Exception:
            pass
        is_drawing_in_progress = False
        return

    ticket_pool = []
    for uid in participants:
        cursor.execute("SELECT tickets FROM users WHERE user_id = ?", (uid,))
        res = cursor.fetchone()
        user_tickets = res[0] if res else 1
        ticket_pool.extend([uid] * user_tickets)

    actual_winners_count = min(winners_count, len(set(ticket_pool))) if ticket_pool else 0
    winners = []
    while len(winners) < actual_winners_count and ticket_pool:
        winner = random.choice(ticket_pool)
        if winner not in winners:
            winners.append(winner)

    prize_per_winner = pool_amount / len(winners) if winners else 0

    winners_mentions_public = []
    winners_db_records = []
    for w_id in winners:
        try:
            member = await bot.get_chat_member(chat_id=CHAT_ID, user_id=w_id)
            name = member.user.full_name
            winners_mentions_public.append(f"• {name}")
            winners_db_records.append(f"• [{name}](tg://user?id={w_id})")
        except Exception:
            winners_mentions_public.append(f"• User ID: {w_id}")
            winners_db_records.append(f"• User ID: `{w_id}`")

    winners_public_text = "\n".join(winners_mentions_public) if winners_mentions_public else "No winners"
    winners_stored_text = "\n".join(winners_db_records) if winners_db_records else "No winners"

    cursor.execute("UPDATE active_giveaways SET status = 'ended', winners_text = ?, ended_at = ? WHERE message_id = ?", (winners_stored_text, ended_at_str, msg_id))
    cursor.execute("UPDATE giveaway_pool SET amount = 0.0 WHERE id = 1")
    cursor.execute("DELETE FROM giveaway_participants")
    
    conn.commit()
    conn.close()

    result_text = (
        "🎉 **UNDRGROUNDZONE GIVEAWAY RESULTS** 🎉\n\n"
        f"💰 **Total Distributed Pool:** `${pool_amount:.2f} USD`\n"
        f"🏆 **Prize for each of the {len(winners)} winners:** **`${prize_per_winner:.2f} USD`**\n\n"
        f"🔥 **Winners:**\n{winners_public_text}\n\n"
        "Congratulations! The giveaway has successfully concluded."
    )

    try:
        await bot.delete_message(chat_id=CHAT_ID, message_id=msg_id)
    except Exception:
        pass
        
    await bot.send_message(chat_id=CHAT_ID, message_thread_id=TOPIC_ID, text=result_text, parse_mode="Markdown")
    is_drawing_in_progress = False

async def giveaway_timer_task(bot: Bot, msg_id: int, duration_hours: float, winners_count: int):
    await asyncio.sleep(duration_hours * 3600)
    await finish_giveaway_automatically(bot, msg_id, winners_count)

async def background_ticker(bot: Bot):
    while True:
        await update_all_active_giveaways(bot)
        await asyncio.sleep(10)

async def set_bot_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="Start the bot"),
        BotCommand(command="tickets", description="Check your tickets"),
        BotCommand(command="ref", description="Get your invite link"),
        BotCommand(command="ebooks", description="Your purchased e-books"),
        BotCommand(command="winners", description="View past giveaway winners"),
        BotCommand(command="help", description="Show help"),
    ]
    await bot.set_my_commands(commands)

@dp.message(Command("winners"))
async def cmd_winners(message: types.Message):
    conn = sqlite3.connect("bot_database.db", timeout=30.0)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT ended_at, winners_text, winners_count 
        FROM active_giveaways 
        WHERE status = 'ended' AND ended_at IS NOT NULL 
        ORDER BY ended_at DESC 
        LIMIT 10
    """)
    past_giveaways = cursor.fetchall()
    conn.close()

    if not past_giveaways:
        await message.answer("📚 No past giveaway records found.")
        return

    response_lines = ["🏆 **Past Giveaway Winners History:**\n"]
    for ended_at_str, winners_text, winners_count in past_giveaways:
        try:
            dt = datetime.fromisoformat(ended_at_str)
            date_formatted = dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            date_formatted = ended_at_str

        response_lines.append(f"📅 **Date:** `{date_formatted}`")
        response_lines.append(f"👥 **Winners ({winners_count}):**\n{winners_text}\n")

    full_response = "\n".join(response_lines)
    
    if len(full_response) > 4000:
        full_response = full_response[:4000] + "\n...(truncated)"

    await message.answer(full_response, parse_mode="Markdown")

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
                        f"🎟 **Included boost:** {tier_data['tickets']} tickets\n"
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
        f"Your current ticket balance: {tickets}\n\n"
        "Use /help to see available commands."
    )
    await message.answer(welcome_text)

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    help_text = (
        "🤖 **Available Commands:**\n\n"
        "📊 /tickets - Check your tickets\n"
        "🔗 /ref - Get your invite link\n"
        "📚 /ebooks - View and download your purchased e-books\n"
        "🏆 /winners - View past giveaway winners history\n"
        "❓ /help - Show help"
    )
    await message.answer(help_text, parse_mode="Markdown")

@dp.message(Command("tickets"))
async def cmd_tickets(message: types.Message):
    user_id = message.from_user.id
    tickets = get_or_create_user(user_id)
    await message.answer(f"Your current ticket balance: {tickets}")

@dp.message(Command("ref"))
async def cmd_ref(message: types.Message):
    user_id = message.from_user.id
    get_or_create_user(user_id)
    
    try:
        chat = await bot.get_chat(CHAT_ID)
        link = chat.invite_link
        
        if not link:
            new_invite = await bot.export_chat_invite_link(chat_id=CHAT_ID)
            link = new_invite
        
        conn = sqlite3.connect("bot_database.db", timeout=30.0)
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO invite_links (invite_link, user_id) VALUES (?, ?)", (link, user_id))
        conn.commit()
        conn.close()
        
        await message.answer(
            f"🔗 **Your permanent invite link:**\n{link}\n\n"
            "Share this link with your friends! When someone joins using it, you get +1 ticket boost.",
            parse_mode="Markdown"
        )
    except Exception as e:
        await message.answer("⚠️ Error generating link. Make sure the bot is an administrator in the group with invite permissions.")
        logging.error(f"Invite link error: {e}")

@dp.message(Command("ebooks"))
async def cmd_ebooks(message: types.Message):
    user_id = message.from_user.id
    conn = sqlite3.connect("bot_database.db", timeout=30.0)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT ebook_name FROM user_ebooks WHERE user_id = ?", (user_id,))
    ebooks = cursor.fetchall()
    conn.close()
    
    if not ebooks:
        await message.answer("📚 You don't have any e-books yet. Check out the store in our group!")
    else:
        ebooks_list = "\n".join([f"• {ebook[0]}" for ebook in ebooks])
        await message.answer(f"📚 **Your purchased e-books:**\n\n{ebooks_list}\n\nSending your files...", parse_mode="Markdown")
        
        name_to_file = {data["name"]: data["file"] for data in TIERS.values()}
        sent_files = set()
        for ebook in ebooks:
            ebook_name = ebook[0]
            filename = name_to_file.get(ebook_name)
            
            if filename and filename not in sent_files:
                if os.path.exists(filename):
                    await message.answer_document(
                        document=FSInputFile(filename),
                        caption=f"🎁 Here is your file: {ebook_name}"
                    )
                    sent_files.add(filename)

@dp.message(Command("add_pool"))
async def cmd_add_pool(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⚠️ Unauthorized.")
        return
        
    args = message.text.split()
    if len(args) < 2:
        await message.answer("⚠️ Usage: `/add_pool <amount>` (e.g., `/add_pool 15`)", parse_mode="Markdown")
        return
        
    try:
        amount_to_add = float(args[1])
    except ValueError:
        await message.answer("⚠️ Please provide a valid number (e.g., `10` or `5.50`).", parse_mode="Markdown")
        return
        
    new_raw_pool = add_to_giveaway_pool_raw(amount_to_add)
    await update_all_active_giveaways(bot)
    
    await message.answer(
        f"✅ **[ADMIN]** Successfully added `${amount_to_add:.2f} USD` to the pool!\n"
        f"📊 Current raw pool in database: `${new_raw_pool:.2f} USD`",
        parse_mode="Markdown"
    )

@dp.message(Command("add_tickets"))
async def cmd_add_tickets(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⚠️ Unauthorized.")
        return
        
    args = message.text.split()
    if len(args) < 3 or not args[1].isdigit() or not args[2].isdigit():
        await message.answer("⚠️ Usage: `/add_tickets <user_id> <tickets_count>` (e.g., `/add_tickets 8998575936 10`)", parse_mode="Markdown")
        return
        
    target_user_id = int(args[1])
    tickets_to_add = int(args[2])
    
    get_or_create_user(target_user_id)
    
    conn = sqlite3.connect("bot_database.db", timeout=30.0)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET tickets = tickets + ? WHERE user_id = ?", (tickets_to_add, target_user_id))
    cursor.execute("SELECT tickets FROM users WHERE user_id = ?", (target_user_id,))
    updated_tickets = cursor.fetchone()[0]
    conn.commit()
    conn.close()
    
    await message.answer(
        f"✅ **[ADMIN]** Successfully added `+{tickets_to_add}` tickets to user `{target_user_id}`!\n"
        f"🎟 User's new ticket balance: **{updated_tickets}**",
        parse_mode="Markdown"
    )

@dp.message(Command("extendgiveaway"))
async def cmd_extend_giveaway(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⚠️ Unauthorized.")
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer("⚠️ Usage: `/extendgiveaway <hours>` (e.g., `/extendgiveaway 5` or `/extendgiveaway -2`)", parse_mode="Markdown")
        return

    try:
        hours_change = float(args[1])
    except ValueError:
        await message.answer("⚠️ Please provide a valid number of hours (e.g., `3` or `-1.5`).", parse_mode="Markdown")
        return

    conn = sqlite3.connect("bot_database.db", timeout=30.0)
    cursor = conn.cursor()
    cursor.execute("SELECT message_id, winners_count, ends_at FROM active_giveaways WHERE status = 'active' ORDER BY message_id DESC LIMIT 1")
    active_gw = cursor.fetchone()
    conn.close()

    if not active_gw:
        await message.answer("⚠️ No active giveaway to modify.")
        return

    msg_id, winners_count, ends_at_str = active_gw
    current_ends_at = datetime.fromisoformat(ends_at_str)
    new_ends_at = current_ends_at + timedelta(hours=hours_change)

    now = datetime.now()
    if new_ends_at <= now:
        await finish_giveaway_automatically(bot, msg_id, winners_count)
        await message.answer("✅ **[ADMIN]** Giveaway time has passed – giveaway has been immediately finished and winners drawn!", parse_mode="Markdown")
    else:
        new_ends_at_str = new_ends_at.isoformat()
        conn = sqlite3.connect("bot_database.db", timeout=30.0)
        cursor = conn.cursor()
        cursor.execute("UPDATE active_giveaways SET ends_at = ? WHERE message_id = ?", (new_ends_at_str, msg_id))
        conn.commit()
        conn.close()

        await update_all_active_giveaways(bot)
        action_word = "extended" if hours_change > 0 else "shortened"
        await message.answer(
            f"✅ **[ADMIN]** Active giveaway has been successfully {action_word} by `{abs(hours_change)}h`!\n"
            f"⏳ New end time: `{new_ends_at.strftime('%Y-%m-%d %H:%M:%S')}`",
            parse_mode="Markdown"
        )

async def process_simulation(message: types.Message, tier_key: str):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        await message.answer("⚠️ Unauthorized.")
        return

    get_or_create_user(user_id)
    
    if tier_key not in TIERS:
        await message.answer("⚠️ Invalid tier!", parse_mode="Markdown")
        return
        
    tier_data = TIERS[tier_key]
    
    conn = sqlite3.connect("bot_database.db", timeout=30.0)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET tickets = tickets + ? WHERE user_id = ?", (tier_data["tickets"], user_id))
    cursor.execute("INSERT INTO user_ebooks (user_id, ebook_name) VALUES (?, ?)", (user_id, tier_data["name"]))
    conn.commit()
    conn.close()
    
    add_to_giveaway_pool_raw(tier_data["price"] * 0.8)
    await update_all_active_giveaways(bot)
    
    conn = sqlite3.connect("bot_database.db", timeout=30.0)
    cursor = conn.cursor()
    cursor.execute("SELECT tickets FROM users WHERE user_id = ?", (user_id,))
    total_tickets = cursor.fetchone()[0]
    conn.close()
    
    await message.answer(
        f"🧪 **[PURCHASE SIMULATION]**\n\n"
        f"✅ Successfully simulated payment for: **{tier_data['name']}**\n"
        f"🎟 Boost tickets added: **+{tier_data['tickets']}**\n"
        f"📊 Your total ticket balance: **{total_tickets}**",
        parse_mode="Markdown"
    )
    
    file_to_send = tier_data["file"]
    if os.path.exists(file_to_send):
        await message.answer_document(
            document=FSInputFile(file_to_send),
            caption=f"🎁 Here is your purchased file for {tier_data['name']}!"
        )

@dp.message(Command("sim_pay"))
async def cmd_sim_pay(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
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

@dp.message(Command("sim_bots"))
async def cmd_sim_bots(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⚠️ Unauthorized.")
        return
        
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await message.answer("⚠️ Usage: `/sim_bots <number>` (e.g., `/sim_bots 4`)", parse_mode="Markdown")
        return
        
    count = int(args[1])
    conn = sqlite3.connect("bot_database.db", timeout=30.0)
    cursor = conn.cursor()
    
    added = 0
    for _ in range(count):
        fake_bot_id = random.randint(900000000, 999999999)
        cursor.execute("INSERT OR IGNORE INTO users (user_id, tickets) VALUES (?, 1)", (fake_bot_id,))
        try:
            cursor.execute("INSERT INTO giveaway_participants (user_id) VALUES (?)", (fake_bot_id,))
            added += 1
        except sqlite3.IntegrityError:
            pass
            
    conn.commit()
    conn.close()
    
    await update_all_active_giveaways(bot)
    await message.answer(f"🤖 Successfully added {added} test bots to the active giveaway!")

@dp.message(Command("startgiveaway"))
async def cmd_start_giveaway(message: types.Message):
    global is_drawing_in_progress

    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⚠️ Unauthorized.")
        return
        
    if is_drawing_in_progress:
        await message.answer("⚠️ Giveaway drawing or startup process is already in progress! Please wait until the current one finishes.")
        return

    args = message.text.split()
    if len(args) < 3 or not args[1].isdigit():
        await message.answer("⚠️ Usage: `/startgiveaway <winners_count> <hours>`\nE.g.: `/startgiveaway 3 24`", parse_mode="Markdown")
        return
        
    winners_count = int(args[1])
    try:
        duration_hours = float(args[2])
    except ValueError:
        await message.answer("⚠️ Provide a valid number of hours (e.g., `12` or `2.5`).", parse_mode="Markdown")
        return

    if not (1 <= winners_count <= 50):
        await message.answer("⚠️ Winners count must be between 1 and 50.")
        return

    is_drawing_in_progress = True
    try:
        conn = sqlite3.connect("bot_database.db", timeout=30.0)
        cursor = conn.cursor()
        cursor.execute("SELECT amount FROM giveaway_pool WHERE id = 1")
        raw_pool_amount = cursor.fetchone()[0]
        pool_amount = get_display_pool(raw_pool_amount)
        
        cursor.execute("DELETE FROM giveaway_participants")
        conn.commit()
        conn.close()

        ends_at = datetime.now() + timedelta(hours=duration_hours)
        ends_at_str = ends_at.isoformat()

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎉 JOIN GIVEAWAY", callback_data="join_giveaway")]
        ])
        
        hours, remainder = divmod(int(duration_hours * 3600), 3600)
        minutes = remainder // 60
        time_str = f"{hours}h {minutes}m"

        text = (
            "🎁 **UNDRGROUNDZONE MEGA GIVEAWAY** 🎁\n\n"
            f"💰 **Current Prize Pool:** `${pool_amount:.2f} USD`\n"
            f"🏆 **Winners Count:** `{winners_count}` (prize split equally)\n"
            f"👥 **Participants:** `0` people\n"
            f"⏳ **Ends in:** `{time_str}`\n\n"
            "💡 *Chcesz zwiększyć swoje szanse? Kupuj e-booki w sklepie lub zapraszaj znajomych za pomocą komendy /ref! Każdy bilet to większa szansa na wygraną.*\n\n"
            "Click the button below to participate!"
        )

        sent_msg = await bot.send_message(
            chat_id=CHAT_ID,
            message_thread_id=TOPIC_ID,
            text=text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )

        conn = sqlite3.connect("bot_database.db", timeout=30.0)
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO active_giveaways (message_id, winners_count, ends_at, status) VALUES (?, ?, ?, 'active')", (sent_msg.message_id, winners_count, ends_at_str))
        conn.commit()
        conn.close()

        asyncio.create_task(giveaway_timer_task(bot, sent_msg.message_id, duration_hours, winners_count))

        await message.answer(f"✅ Giveaway successfully started for {duration_hours}h!")
    except Exception as e:
        is_drawing_in_progress = False
        await message.answer(f"⚠️ Error starting giveaway: {e}")

@dp.message(Command("endgiveaway"))
async def cmd_end_giveaway(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⚠️ Unauthorized.")
        return

    conn = sqlite3.connect("bot_database.db", timeout=30.0)
    cursor = conn.cursor()
    cursor.execute("SELECT message_id, winners_count FROM active_giveaways WHERE status = 'active' ORDER BY message_id DESC LIMIT 1")
    active_gw = cursor.fetchone()
    conn.close()

    if not active_gw:
        await message.answer("⚠️ No active giveaway to finish.")
        return

    msg_id, winners_count = active_gw
    await finish_giveaway_automatically(bot, msg_id, winners_count)
    await message.answer("✅ Giveaway prematurely ended and winners drawn!")

@dp.callback_query(lambda c: c.data == "join_giveaway")
async def process_join_giveaway(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    get_or_create_user(user_id)
    
    conn = sqlite3.connect("bot_database.db", timeout=30.0)
    cursor = conn.cursor()
    
    cursor.execute("SELECT 1 FROM giveaway_participants WHERE user_id = ?", (user_id,))
    already_joined = cursor.fetchone()
    
    if already_joined:
        conn.close()
        await bot.answer_callback_query(
            callback_query.id, 
            text="⚠️ You have already joined this giveaway!", 
            show_alert=True
        )
        return

    try:
        cursor.execute("INSERT INTO giveaway_participants (user_id) VALUES (?)", (user_id,))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        await bot.answer_callback_query(
            callback_query.id, 
            text="⚠️ You have already joined this giveaway!", 
            show_alert=True
        )
        return

    conn.close()

    await bot.answer_callback_query(callback_query.id, text="✅ Success! You joined the giveaway.", show_alert=False)
    await update_all_active_giveaways(bot)

@dp.message(Command("post_ebooks"))
async def cmd_post_ebooks(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⚠️ Unauthorized.")
        return

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
                    message_thread_id=STORE_TOPIC_ID,
                    photo=FSInputFile(data["photo"]),
                    caption=caption_text,
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
            else:
                await bot.send_message(
                    chat_id=CHAT_ID,
                    message_thread_id=STORE_TOPIC_ID,
                    text=f"⚠️ [Image `{data['photo']}` missing]\n\n" + caption_text,
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
        except Exception as e:
            await message.answer(f"⚠️ Error posting {data['name']}: {e}")
            return

    await message.answer("✅ Store successfully posted to the e-books topic (3) with individual images!")

@dp.chat_member()
async def member_join(event: ChatMemberUpdated):
    if event.chat.username and f"@{event.chat.username.lower()}" == CHAT_ID.lower():
        if event.new_chat_member.status == "member" and event.old_chat_member.status in ["left", "kicked"]:
            new_user_id = event.new_chat_member.user.id
            invite_link_obj = event.invite_link
            
            if invite_link_obj and invite_link_obj.invite_link:
                link_url = invite_link_obj.invite_link
                
                conn = sqlite3.connect("bot_database.db", timeout=30.0)
                cursor = conn.cursor()
                cursor.execute("SELECT user_id FROM invite_links WHERE invite_link = ?", (link_url,))
                row = cursor.fetchone()
                
                if row:
                    inviter_id = row[0]
                    if inviter_id != new_user_id:
                        conn_db = sqlite3.connect("bot_database.db", timeout=30.0)
                        cursor_db = conn_db.cursor()
                        cursor_db.execute("SELECT 1 FROM referral_history WHERE inviter_id = ? AND invited_id = ?", (inviter_id, new_user_id))
                        already_referred = cursor_db.fetchone()
                        
                        if not already_referred:
                            cursor_db.execute("INSERT INTO referral_history (inviter_id, invited_id) VALUES (?, ?)", (inviter_id, new_user_id))
                            cursor_db.execute("UPDATE users SET tickets = tickets + 1 WHERE user_id = ?", (inviter_id,))
                            conn_db.commit()
                            
                            cursor_db.execute("SELECT tickets FROM users WHERE user_id = ?", (inviter_id,))
                            inviter_tickets = cursor_db.fetchone()[0]
                            conn_db.close()
                            
                            try:
                                await bot.send_message(
                                    inviter_id,
                                    f"🎉 Someone joined the group using your invite link!\n"
                                    f"You received +1 ticket boost for the giveaway.\n"
                                    f"Your total ticket balance: {inviter_tickets}"
                                )
                            except Exception:
                                pass
                conn.close()

            get_or_create_user(new_user_id)
            try:
                await bot.send_message(
                    new_user_id,
                    "👋 Welcome to the group! You have received your base 1 token."
                )
            except Exception:
                pass

async def main():
    print("URUCHAMIAM BOTA...")
    logging.basicConfig(level=logging.INFO)
    
    await start_web_server()
    
    await set_bot_commands(bot)
    asyncio.create_task(background_ticker(bot))
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
