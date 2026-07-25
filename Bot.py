import asyncio
import logging
import sqlite3
import os
import random
import pathlib
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
TOPIC_ID = 2          
STORE_TOPIC_ID = 3    

ADMIN_IDS = [8998575936]

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

async def handle_mini_app(request):
    html_path = pathlib.Path(__file__).parent / "templates" / "index.html"
    if html_path.exists():
        return web.FileResponse(html_path)
    return web.Response(text="index.html not found", status=404)

async def api_get_user(request):
    user_id = int(request.match_info.get("user_id", 0))
    conn = sqlite3.connect("bot_database.db", timeout=30.0)
    cursor = conn.cursor()
    cursor.execute("SELECT tickets FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    
    cursor.execute("SELECT COUNT(*) FROM referral_history WHERE inviter_id = ?", (user_id,))
    ref_count = cursor.fetchone()[0]

    cursor.execute("SELECT amount FROM giveaway_pool WHERE id = 1")
    pool_row = cursor.fetchone()
    raw_pool = pool_row[0] if pool_row else 0.0
    pool_amount = raw_pool if raw_pool >= 15.0 else 15.0

    conn.close()
    
    tickets = row[0] if row else 1
    return web.json_response({
        "user_id": user_id,
        "points": tickets,
        "referrals_count": ref_count,
        "pool_amount": pool_amount
    })

async def api_get_leaderboard(request):
    conn = sqlite3.connect("bot_database.db", timeout=30.0)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, tickets FROM users ORDER BY tickets DESC LIMIT 10")
    rows = cursor.fetchall()
    
    cursor.execute("""
        SELECT ended_at, winners_text, winners_count 
        FROM active_giveaways 
        WHERE status = 'ended' AND ended_at IS NOT NULL 
        ORDER BY ended_at DESC 
        LIMIT 5
    """)
    past_winners = cursor.fetchall()
    conn.close()
    
    leaderboard_data = [{"user_id": r[0], "points": r[1]} for r in rows]
    winners_data = []
    for pw in past_winners:
        winners_data.append({
            "ended_at": pw[0],
            "winners_text": pw[1],
            "winners_count": pw[2]
        })

    return web.json_response({
        "leaderboard": leaderboard_data,
        "past_winners": winners_data
    })

async def api_admin_action(request):
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"message": "Invalid JSON"}, status=400)

    user_id = int(data.get("user_id", 0))
    if user_id not in ADMIN_IDS:
        return web.json_response({"message": "Unauthorized"}, status=403)

    action = request.match_info.get("action", "")

    if action == "start":
        success = await trigger_start_giveaway_internal(3, 24.0)
        if success:
            return web.json_response({"message": "Giveaway successfully started!"})
        else:
            return web.json_response({"message": "Giveaway already in progress or error!"}, status=400)

    elif action == "add_pool":
        text_val = data.get("text", "")
        try:
            cleaned = "".join([c for c in str(text_val) if c.isdigit() or c == "."])
            amount = float(cleaned) if cleaned else 15.0
        except ValueError:
            amount = 15.0

        add_to_giveaway_pool_raw(amount)
        await update_all_active_giveaways(bot)
        return web.json_response({"message": f"Successfully added {amount} to pool!"})

    elif action == "add_tickets":
        try:
            target_id = int(data.get("target_id", 0))
            count = int(data.get("count", 0))
        except (ValueError, TypeError):
            return web.json_response({"message": "Invalid target ID or ticket count"}, status=400)

        get_or_create_user(target_id)
        conn = sqlite3.connect("bot_database.db", timeout=30.0)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET tickets = tickets + ? WHERE user_id = ?", (count, target_id))
        conn.commit()
        conn.close()
        return web.json_response({"message": f"Successfully added {count} tickets to {target_id}!"})

    elif action == "winners":
        conn = sqlite3.connect("bot_database.db", timeout=30.0)
        cursor = conn.cursor()
        cursor.execute("SELECT message_id, winners_count FROM active_giveaways WHERE status = 'active' ORDER BY message_id DESC LIMIT 1")
        active_gw = cursor.fetchone()
        conn.close()

        if not active_gw:
            return web.json_response({"message": "No active giveaway to draw!"}, status=400)

        msg_id, winners_count = active_gw
        await finish_giveaway_automatically(bot, msg_id, winners_count)
        return web.json_response({"message": "Giveaway drawn successfully!"})

    return web.json_response({"message": "Unknown action"}, status=404)

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle)
    app.router.add_get("/webapp", handle_mini_app)
    app.router.add_get("/api/user/{user_id}", api_get_user)
    app.router.add_get("/api/leaderboard", api_get_leaderboard)
    app.router.add_post("/api/admin/{action}", api_admin_action)
    
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

async def check_membership(user_id: int, bot_instance: Bot) -> bool:
    try:
        member = await bot_instance.get_chat_member(chat_id=CHAT_ID, user_id=user_id)
        if member.status in ['member', 'administrator', 'creator']:
            return True
    except Exception as e:
        logging.error(f"Błąd sprawdzania członkostwa dla {user_id}: {e}")
    return False

async def route_user_response(message: types.Message, text_to_send: str, reply_markup=None, parse_mode: str = None):
    if message.chat.type != "private":
        try:
            await bot.send_message(message.from_user.id, text_to_send, reply_markup=reply_markup, parse_mode=parse_mode)
            await message.answer(f"@{message.from_user.username or message.from_user.first_name}, sprawdziłem! Odpowiedź została wysłana do Ciebie w wiadomości prywatnej (DM). 📬")
        except Exception:
            await message.answer(f"@{message.from_user.username or message.from_user.first_name}, nie mogłem wysłać Ci wiadomości prywatnej. Odblokuj bota @Giveaway63bot! ⚠️")
    else:
        await message.answer(text_to_send, reply_markup=reply_markup, parse_mode=parse_mode)

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
            "⚠️ **WARNING:** You must be a member of the group to enter and stay in the giveaway!\n\n"
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
        if await check_membership(uid, bot):
            cursor.execute("SELECT tickets FROM users WHERE user_id = ?", (uid,))
            res = cursor.fetchone()
            user_tickets = res[0] if res else 1
            ticket_pool.extend([uid] * user_tickets)
        else:
            cursor.execute("DELETE FROM giveaway_participants WHERE user_id = ?", (uid,))

    actual_winners_count = min(winners_count, len(set(ticket_pool))) if ticket_pool else 0
    winners = []
    while len(winners) < actual_winners_count and ticket_pool:
        winner = random.choice(ticket_pool)
        if winner not in winners:
            winners.append(winner)

    prize_per_winner = pool_amount / len(winners) if winners else 0

    winners_mentions_public = []
    winners_db_records = []
    admin_private_lines = [f"🏆 **Giveaway Ended - Winners Summary:**\n"]

    for w_id in winners:
        try:
            member = await bot.get_chat_member(chat_id=CHAT_ID, user_id=w_id)
            name = member.user.full_name
            winners_mentions_public.append(f"• {name}")
            winners_db_records.append(f"• {name}")
            admin_private_lines.append(f"• {name} (ID: {w_id})")
        except Exception:
            winners_mentions_public.append(f"• User ID: {w_id}")
            winners_db_records.append(f"• User ID: {w_id}")
            admin_private_lines.append(f"• User ID: {w_id}")

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
        f"🏆 **Prize for each winner:** **`${prize_per_winner:.2f} USD`**\n\n"
        f"🔥 **Winners:**\n{winners_public_text}\n\n"
        "Congratulations!"
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
        BotCommand(command="help", description="Show help"),
    ]
    await bot.set_my_commands(commands)

async def trigger_start_giveaway_internal(winners_count: int, duration_hours: float) -> bool:
    global is_drawing_in_progress
    if is_drawing_in_progress:
        return False

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
        return True
    except Exception as e:
        is_drawing_in_progress = False
        logging.error(f"Error starting giveaway: {e}")
        return False

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
                    
                    pay_text = (
                        f"🛒 **Generating payment for {tier_data['name']}**\n\n"
                        f"🎟 **Included boost:** {tier_data['tickets']} tickets\n"
                        f"💰 **Amount:** ${tier_data['price']} USD\n\n"
                        "Click below to pay:"
                    )
                    await route_user_response(message, pay_text, reply_markup=pay_keyboard, parse_mode="Markdown")
                except Exception as e:
                    await route_user_response(message, "⚠️ Error generating payment.")
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
                ]
            ])
            select_text = f"💱 **Choose cryptocurrency for {TIERS[clean_payload]['name']} (${TIERS[clean_payload]['price']}):**"
            await route_user_response(message, select_text, reply_markup=select_keyboard, parse_mode="Markdown")
            return

    tickets = get_or_create_user(user_id)
    await route_user_response(message, f"👋 Welcome to Undrgroundzone!\nYour tickets: {tickets}")

@dp.callback_query(lambda c: c.data == "join_giveaway")
async def process_join_giveaway(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if not await check_membership(user_id, bot):
        await bot.answer_callback_query(callback_query.id, text="⚠️ You must be a group member!", show_alert=True)
        return

    get_or_create_user(user_id)
    conn = sqlite3.connect("bot_database.db", timeout=30.0)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM giveaway_participants WHERE user_id = ?", (user_id,))
    if cursor.fetchone():
        conn.close()
        await bot.answer_callback_query(callback_query.id, text="⚠️ Already joined!", show_alert=True)
        return

    cursor.execute("INSERT INTO giveaway_participants (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()
    await bot.answer_callback_query(callback_query.id, text="✅ Joined giveaway successfully!", show_alert=False)
    await update_all_active_giveaways(bot)

@dp.chat_member()
async def member_join(event: ChatMemberUpdated):
    if event.chat.username and f"@{event.chat.username.lower()}" == CHAT_ID.lower():
        if event.new_chat_member.status == "member" and event.old_chat_member.status in ["left", "kicked"]:
            get_or_create_user(event.new_chat_member.user.id)

async def main():
    print("STARTING BOT...")
    logging.basicConfig(level=logging.INFO)
    await start_web_server()
    await set_bot_commands(bot)
    asyncio.create_task(background_ticker(bot))
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
