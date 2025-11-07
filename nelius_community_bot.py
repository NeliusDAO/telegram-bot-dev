import asyncio
import os
import re
import logging
import requests
import sqlite3
import json
import redis
from dotenv import load_dotenv
from telegram import BotCommand, Update, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, MessageHandler, CommandHandler, ConversationHandler, ContextTypes, filters

from generate_and_load_ids import load_to_redis  # import your Social ID loader
from assign_social_id import assign_social_id  # import your Social ID assignment function
from nelius_dev import addevent, removeevent, updatepub, allocate  # import dev-only commands
from set_social_media_handles import setx  # import social media handle setter
from set_contact_info import PHONE_ENTRY, add_phone, save_phone, cancel # import phone number handlers

load_dotenv()

DB_PATH = "neliusdao.db"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
REDIS_URL = os.getenv("REDIS_URL")
COMMUNITY_LINK = "https://t.me/+P9j1f85xo1ExZTk0"
WEBHOOK_URL = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/{TELEGRAM_BOT_TOKEN}"
PORT = int(os.getenv("PORT", 8080))

# Connect to Redis
redis_client = redis.from_url(REDIS_URL, decode_responses=True)


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER UNIQUE,
        social_id TEXT UNIQUE,
        phone_number TEXT,
        points INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
""")

    cursor.execute("""CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        publicity_score INTEGER DEFAULT 0
    )""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS social_handles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        platform TEXT NOT NULL,
        handle TEXT,
        UNIQUE(user_id, platform),
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """)

    conn.commit()
    conn.close()


# ------------------------
# Helper Functions
# ------------------------

def cache_user_profile(user_id: int, social_id: str, points: int):
    """Save user profile to Redis cache."""
    redis_client.setex(f"user:{user_id}", 3600, json.dumps({"social_id": social_id, "points": points}))


def get_cached_user_profile(user_id: int):
    """Retrieve cached user profile, return None if not found."""
    cached = redis_client.get(f"user:{user_id}")
    return json.loads(cached) if cached else None


def cache_events_list(events: list):
    """Cache events list for 10 minutes."""
    redis_client.setex("events:list", 600, json.dumps(events))


def get_cached_events_list():
    cached = redis_client.get("events:list")
    return json.loads(cached) if cached else None


# ------------------------
# Telegram Bot Commands
# ------------------------
MAIN_MENU = ReplyKeyboardMarkup(
    [
        ["🪪 My ID","🏆 My Points"],
        ["🎉 Events","👤 My Profile"],
    ],
    resize_keyboard=True,
    one_time_keyboard=False,
    is_persistent=True
)

async def set_bot_commands(app):
    commands = [
        BotCommand("start", "Show main menu"),
        BotCommand("setx", "Set your X (Twitter) handle"),
        BotCommand("addphone", "Add your phone number for giveaways"),
        BotCommand("joincommunity", "Join the Nelius community"),
    ]
    await app.bot.set_my_commands(commands)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT social_id, points FROM users WHERE telegram_id=?", (user_id,))
    row = cursor.fetchone()

    if not row:
        # ✅ Use your generator instead of f"NEL-{user_id % 10000}"
        social_id = assign_social_id(user_id)
        cursor.execute(
            "INSERT INTO users (telegram_id, social_id) VALUES (?, ?)",
            (user_id, social_id)
        )
        conn.commit()
        points = 0
        msg = f"👋 Welcome to Nelius DAO!\nYour Social ID: {social_id}"
    else:
        social_id, points = row
        msg = f"👋 Welcome back!\nYour Social ID: {social_id}\n🏆 Points: {points}"

    conn.close()

    # Cache the profile in Redis
    cache_user_profile(user_id, social_id, points)
    
    # --- Create button menu ---
    # keyboard = [
    #     [KeyboardButton("🪪 My ID"), KeyboardButton("🏆 My Points")],
    #     [KeyboardButton("🎉 Events"), KeyboardButton("👤 My Profile")]
    # ]
    # reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await update.message.reply_text(msg, reply_markup=MAIN_MENU)


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    profile = get_cached_user_profile(user_id)
    if not profile:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT social_id, points FROM users WHERE telegram_id=?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            await update.message.reply_text("⚠️ You are not registered yet. Use /start to join Nelius.")
            return
        social_id, points = row
        cache_user_profile(user_id, social_id, points)
    else:
        social_id = profile["social_id"]

    await update.message.reply_text(f"🪪 Your Nelius Social ID: {social_id}")


async def mypoints(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    profile = get_cached_user_profile(user_id)

    if not profile:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT social_id, points FROM users WHERE telegram_id=?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            await update.message.reply_text("⚠️ You are not registered yet. Use /start to join Nelius.")
            return
        social_id, points = row
        cache_user_profile(user_id, social_id, points)
    else:
        points = profile["points"]

    await update.message.reply_text(f"🏆 Your Nelius Points: {points}")


async def events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    events_data = get_cached_events_list()

    if not events_data:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, publicity_score FROM events ORDER BY id DESC")
        rows = cursor.fetchall()
        conn.close()

        events_data = [{"id": eid, "title": title, "score": score} for eid, title, score in rows]
        cache_events_list(events_data)

    if not events_data:
        await update.message.reply_text("📭 No active events yet.")
        return

    msg = "🎉 *Nelius Events:*\n\n"
    for e in events_data:
        msg += f"• {e['title']} — 🗣️ Publicity Score: {e['score']}\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT u.social_id, u.points, s.handle
        FROM users u
        LEFT JOIN social_handles s ON u.id = s.user_id AND s.platform='x'
        WHERE u.telegram_id=?
    """, (update.effective_user.id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        await update.message.reply_text("⚠️ You don't have a profile yet. Use /start first.")
        return

    social_id, points, x_handle = row
    handle_display = x_handle if x_handle else "❌ Not set"

    msg = (
        f"👤 <b>Nelius Profile</b>\n"
        f"🪪 Social ID: <code>{social_id}</code>\n"
        f"🏆 Points: {points}\n"
        f"🐦 X Handle: {handle_display}"
    )
    await update.message.reply_text(msg, parse_mode="HTML")

# async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     """Display user's profile: social ID, points, and top events."""
#     user_id = update.effective_user.id

#     profile = get_cached_user_profile(user_id)
#     if not profile:
#         conn = sqlite3.connect(DB_PATH)
#         cursor = conn.cursor()
#         cursor.execute("SELECT social_id, points FROM users WHERE telegram_id=?", (user_id,))
#         user = cursor.fetchone()
#         if not user:
#             conn.close()
#             await update.message.reply_text("⚠️ You are not registered yet. Use /start to create your Nelius profile.")
#             return
#         social_id, points = user
#         cache_user_profile(user_id, social_id, points)
#     else:
#         social_id, points = profile["social_id"], profile["points"]

#     events_data = get_cached_events_list()
#     if not events_data:
#         conn = sqlite3.connect(DB_PATH)
#         cursor = conn.cursor()
#         cursor.execute("SELECT title, publicity_score FROM events ORDER BY publicity_score DESC LIMIT 3")
#         rows = cursor.fetchall()
#         events_data = [{"title": title, "score": score} for title, score in rows]
#         cache_events_list(events_data)
#         conn.close()

#     msg = f"🌐 *Your Nelius Profile*\n\n"
#     msg += f"🪪 Social ID: `{social_id}`\n"
#     msg += f"🏆 Points: *{points}*\n"

#     if events_data:
#         msg += "🎯 *Top Events Supported by Nelius:*\n"
#         for e in events_data[:3]:
#             msg += f"• {e['title']} — 🔊 {e['score']}\n"
#     else:
#         msg += "📭 No events yet. Check back later!"

#     await update.message.reply_text(msg, parse_mode="Markdown")

async def join_community(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🚀 Tap below to join our community:\n\n{COMMUNITY_LINK}"
    )

# --- Button text handler ---
async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "🪪 My ID":
        await myid(update, context)
    elif text == "🏆 My Points":
        await mypoints(update, context)
    elif text == "🎉 Events":
        await events(update, context)
    elif text == "👤 My Profile":
        await profile(update, context)

# ------------------------
# Main Entry Point
# ------------------------
async def main():
    init_db()
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("mypoints", mypoints))
    app.add_handler(CommandHandler("events", events))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("setx", setx))
    app.add_handler(CommandHandler("joincommunity", join_community))

    # Button interactions
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))
    
    # Phone Number Conversation
    # add_phone_handler = ConversationHandler(
    #     entry_points=[CommandHandler("addphone", add_phone)],
    #     states={
    #         OTP_ENTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, verify_phone)],
    #         "CONFIRM_OTP": [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_otp)]
    #     },
    #     fallbacks=[CommandHandler("cancel", cancel)]
    # )
    add_phone_handler = ConversationHandler(
    entry_points=[CommandHandler("addphone", add_phone)],
    states={
        PHONE_ENTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_phone)]
    },
    fallbacks=[CommandHandler("cancel", cancel)]
    )

    app.add_handler(add_phone_handler)
    
    # Dev commands (from nelius_dev.py)
    app.add_handler(CommandHandler("addevent", addevent))
    app.add_handler(CommandHandler("removeevent", removeevent))
    app.add_handler(CommandHandler("updatepub", updatepub))
    app.add_handler(CommandHandler("allocate", allocate))

    print("Nelius DAO Bot is running...")

    await set_bot_commands(app)

    # === WEBHOOK SETUP ===
    # === WEBHOOK CONFIG ===
    port = int(os.getenv("PORT", PORT))
    await app.bot.delete_webhook()
    await app.bot.set_webhook(WEBHOOK_URL)

    print(f"Webhook set at {WEBHOOK_URL} listening on port {port}...")

    # 👇 FIXED PART
    # run_webhook() tries to close loop internally — Render keeps it alive.
    # So we just run the internal webhook startup manually:
    await app.initialize()
    await app.start()
    await app.updater.start_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=TELEGRAM_BOT_TOKEN,
        webhook_url=WEBHOOK_URL,
    )

    print("Webhook server running. Waiting for Telegram updates...")

    # Keep it running forever
    await asyncio.Event().wait()

if __name__ == "__main__":
    load_to_redis()  # Preload Social IDs into Redis
    asyncio.run(main())