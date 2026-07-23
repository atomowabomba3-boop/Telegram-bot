import asyncio
import logging
import sqlite3
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, ChatMemberUpdated, InlineKeyboardMarkup, InlineKeyboardButton
from CryptoPayAPI.AioCryptoPay import AioCryptoPay
from CryptoPayAPI.types.asset import USDT

TOKEN = "8795322916:AAHg7sfezoa-xTYk1Dp1xRW8xBwJnY1FAts"
CRYPTO_PAY_TOKEN = "612964:AAtkz79Sjrh5hks8knampljxXpnzRpS94Hz"  # Twój token CryptoBot
CHAT_ID = "@Undrgroundzone"
TOPIC_ID = 3  # ID Twojego topiku w grupie

bot = Bot(token=TOKEN)
# Inicjalizacja CryptoBota (zmień is_test_net=False, gdy przechodzisz na prawdziwe płatności mainnet)
crypto = AioCryptoPay(token=CRYPTO_PAY_TOKEN, is_test_net=False)

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
        BotCommand(command="start", description="Start bota"),
        BotCommand(command="tickets", description="Sprawdź swoje losy"),
        BotCommand(command="ref", description="Pobierz link zaproszeniowy"),
        BotCommand(command="ebooks", description="Twoje zakupy"),
        BotCommand(command="post_ebooks", description="Wyślij sklep na topik"),
        BotCommand(command="help", description="Pomoc"),
    ]
    await bot.set_my_commands(commands)

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    args = message.text.split()
    
    if len(args) > 1:
        payload = args[1]
        tiers = {
            "buy_tier1": {"name": "Ebook Tier 1", "price": 2.0},
            "buy_tier2": {"name": "Ebook Tier 2", "price": 5.0},
            "buy_tier3": {"name": "Ebook Tier 3", "price": 10.0}
        }
        
        if payload in tiers:
            tier_data = tiers[payload]
            try:
                # Tworzenie faktury w CryptoBocie (w walucie USDT)
                invoice = await crypto.create_invoice(
                    amount=tier_data["price"],
                    asset=USDT,
                    description=f"Zakup: {tier_data['name']} + losy w Undrgroundzone",
                    payload=payload
                )
                
                pay_keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="💳 OPŁAĆ W CRYPTO", url=invoice.bot_invoice_url)]
                ])
                
                await message.answer(
                    f"🛒 **Generowanie płatności dla {tier_data['name']}**\n\n"
                    f"💰 **Kwota:** ${tier_data['price']} USDT\n\n"
                    "Kliknij poniższy przycisk, aby przejść do bezpiecznej bramki płatności CryptoBot i opłacić zamówienie:",
                    reply_markup=pay_keyboard,
                    parse_mode="Markdown"
                )
            except Exception as e:
                await message.answer("⚠️ Wystąpił błąd podczas generowania płatności. Spróbuj ponownie później.")
                logging.error(f"CryptoPay error: {e}")
            return

    tickets = get_or_create_user(user_id)
    welcome_text = (
        "👋 Witaj w systemie Undrgroundzone!\n\n"
        "Tutaj możesz sprawdzić swoje losy, link zaproszeniowy oraz odebrać e-booki.\n\n"
        f"Twoje saldo losów: {tickets}\n\n"
        "Użyj /help, aby zobaczyć komendy."
    )
    await message.answer(welcome_text)

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    help_text = (
        "🤖 **Dostępne komendy:**\n\n"
        "📊 /tickets - Sprawdź saldo losów\n"
        "🔗 /ref - Pobierz link zaproszeniowy\n"
        "📚 /ebooks - Zobacz zakupione e-booki\n"
        "🛒 /post_ebooks - Wyślij sklep na grupę\n"
        "❓ /help - Pomoc"
    )
    await message.answer(help_text, parse_mode="Markdown")

@dp.message(Command("tickets"))
async def cmd_tickets(message: types.Message):
    user_id = message.from_user.id
    tickets = get_or_create_user(user_id)
    await message.answer(f"Twoje aktualne saldo losów:\n- Łącznie losów: {tickets}")

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
            f"🔗 **Twój osobisty link zaproszeniowy:**\n{link}\n\n"
            "Udostępnij go znajomym! Gdy ktoś dołączy przez ten link, automatycznie otrzymasz los.",
            parse_mode="Markdown"
        )
    except Exception as e:
        await message.answer("⚠️ Błąd generowania linku. Upewnij się, że bot jest administratorem w grupie.")
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
        await message.answer("📚 Nie masz jeszcze żadnych e-booków. Sprawdź sklep na naszej grupie!")
    else:
        ebooks_list = "\n".join([f"• {ebook[0]}" for ebook in ebooks])
        await message.answer(f"📚 **Twoje zakupione e-booki:**\n\n{ebooks_list}", parse_mode="Markdown")

@dp.message(Command("post_ebooks"))
async def cmd_post_ebooks(message: types.Message):
    photo_green = "ebook_green.png.jpg"
    photo_blue = "ebook_blue.png.jpg"
    photo_purple = "ebook_purple.png.jpg"

    caption_1 = (
        "🟢 **Ebook Tier 1**\n"
        "Pakiet podstawowy dla początkujących.\n\n"
        "🎟 **W zestawie:** 50 losów\n"
        "💰 **Cena:** $2 USD"
    )
    keyboard_1 = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 KUP TIER 1 ($2)", url="https://t.me/Undrgroundzone_bot?start=buy_tier1")]
    ])

    caption_2 = (
        "🔵 **Ebook Tier 2**\n"
        "Pakiet średni z rozszerzonymi materiałami.\n\n"
        "🎟 **W zestawie:** 200 losów\n"
        "💰 **Cena:** $5 USD"
    )
    keyboard_2 = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 KUP TIER 2 ($5)", url="https://t.me/Undrgroundzone_bot?start=buy_tier2")]
    ])

    caption_3 = (
        "🟣 **Ebook Tier 3**\n"
        "Pakiet elitarny – pełen dostęp i maksymalne korzyści.\n\n"
        "🎟 **W zestawie:** 500 losów\n"
        "💰 **Cena:** $10 USD"
    )
    keyboard_3 = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 KUP TIER 3 ($10)", url="https://t.me/Undrgroundzone_bot?start=buy_tier3")]
    ])

    try:
        await bot.send_photo(chat_id=CHAT_ID, message_thread_id=TOPIC_ID, photo=types.FSInputFile(photo_green), caption=caption_1, reply_markup=keyboard_1, parse_mode="Markdown")
        await bot.send_photo(chat_id=CHAT_ID, message_thread_id=TOPIC_ID, photo=types.FSInputFile(photo_blue), caption=caption_2, reply_markup=keyboard_2, parse_mode="Markdown")
        await bot.send_photo(chat_id=CHAT_ID, message_thread_id=TOPIC_ID, photo=types.FSInputFile(photo_purple), caption=caption_3, reply_markup=keyboard_3, parse_mode="Markdown")
        await message.answer("✅ Sklep został pomyślnie wysłany na topik grupy!")
    except Exception as e:
        await message.answer(f"⚠️ Błąd wysyłania: {e}")

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
                                f"🎉 Ktoś dołączył do grupy przez Twój link zaproszeniowy!\n"
                                f"Twoje nowe saldo losów: {inviter_tickets}"
                            )
                        except Exception:
                            pass

            get_or_create_user(new_user_id)
            try:
                await bot.send_message(
                    new_user_id,
                    "👋 Witaj w grupie! Otrzymałeś swój początkowy los."
                )
            except Exception:
                pass

async def main():
    logging.basicConfig(level=logging.INFO)
    await set_bot_commands(bot)
    await crypto.close()  # Na koniec zamknięcie sesji
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
