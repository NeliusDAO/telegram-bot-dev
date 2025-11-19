import asyncio
import os
import re
import logging
import requests
import sqlite3
import json
import psycopg2
import redis
from dotenv import load_dotenv
from telegram import (BotCommand, BotCommandScopeDefault, BotCommandScopeAllPrivateChats, Update, KeyboardButton, ReplyKeyboardMarkup, 
                    ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup)
from telegram.ext import (Application, MessageHandler, CommandHandler, ConversationHandler,
                          CallbackQueryHandler, ContextTypes, filters)

from settings import DATABASE_URL, TELEGRAM_BOT_TOKEN, TELEGRAM_COMMUNITY_LINK, WHATSAPP_COMMUNITY_LINK, WEBHOOK_URL, PORT, REDIS_URL, get_db_connection
from generate_and_load_ids import load_to_redis  # import your Social ID loader
from assign_social_id import assign_social_id  # import your Social ID assignment function
from nelius_dev import addevent, updateevent, removeevent, updatepub, allocate, dump_db  # import dev-only commands
from set_social_media_handles import setx, setig, settiktok  # import social media handle setter
from set_contact_info import PHONE_ENTRY, add_or_update_phone, save_phone, cancel # import phone number handlers

load_dotenv()

# Connect to Redis
redis_client = redis.from_url(REDIS_URL, decode_responses=True)


def init_db():    
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        telegram_id BIGINT UNIQUE,
        social_id TEXT UNIQUE,
        phone_number TEXT,
        points INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS events (
    id SERIAL PRIMARY KEY,
    title TEXT,
    instagram_link TEXT,
    x_link TEXT,
    tik_tok_link TEXT,
    publicity_score INTEGER DEFAULT 0
    )
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS social_handles (
        id SERIAL PRIMARY KEY,
        user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
        social_id TEXT REFERENCES users(social_id) ON DELETE CASCADE,
        platform TEXT NOT NULL,
        handle TEXT,
        UNIQUE(user_id, platform)
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

async def set_bot_commands(app, telegram_id=None):
    commands = [
        BotCommand("start", "Show main menu"),
        BotCommand("setx", "Set your X (Twitter) handle"),
        BotCommand("setig", "Set your Instagram handle"),
        BotCommand("addphone", "Add your phone number"),
        BotCommand("jointelegramcommunity", "Join our Telegram community"),
        BotCommand("joinwhatsappcommunity", "Join our WhatsApp community"),
    ]
    await app.bot.set_my_commands(commands, scope=BotCommandScopeDefault())
    
    # For all private chats (so users only see these commands in DM with bot)
    await app.bot.set_my_commands(commands, scope=BotCommandScopeAllPrivateChats())


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT social_id, points FROM users WHERE telegram_id=%s",
        (user_id,)
    )
    row = cursor.fetchone()

    if not row:
        social_id = assign_social_id(user_id)
        cursor.execute(
            "INSERT INTO users (telegram_id, social_id) VALUES (%s, %s)",
            (user_id, social_id)
        )
        conn.commit()
        points = 0
        msg = f"👋 Welcome to Nelius DAO!\nYour Social ID: {social_id}"
    else:
        social_id, points = row
        msg = f"👋 Welcome back!\nYour Social ID: {social_id}\n🏆 Points: {points}"

    conn.close()

    cache_user_profile(user_id, social_id, points)
    await update.message.reply_text(msg, reply_markup=MAIN_MENU)


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    profile = get_cached_user_profile(user_id)
    if not profile:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT social_id, points FROM users WHERE telegram_id=%s", 
            (user_id,)
        )
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
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT social_id, points FROM users WHERE telegram_id=%s", 
            (user_id,)
        )
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
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, title, publicity_score FROM events ORDER BY id DESC"
        )
        rows = cursor.fetchall()
        conn.close()

        events_data = [
            {"id": eid, "title": title, "score": score} for eid, title, score in rows
        ]
        cache_events_list(events_data)

    if not events_data:
        msg = "📭 No active events yet."
        keyboard = None
    else:
        msg = "🎉 *Nelius Events*\nTap an event below to view boost links."
        keyboard = [
            [
                InlineKeyboardButton(
                    f"{e['title']} — ⭐ {e['score']}",
                    callback_data=f"event_{e['id']}"
                )
            ]
            for e in events_data
        ]

    if update.message:
        # Called via /events command
        await update.message.reply_text(
            msg,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None
        )
    elif update.callback_query:
        # Called via Back button or other callback
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(
            msg,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None
        )


async def event_detail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    if not data.startswith("event_"):
        return

    event_id = int(data.split("_")[1])

    # Fetch event info
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT title, publicity_score, instagram_link, x_link FROM events WHERE id = %s",
        (event_id,)
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        await query.edit_message_text("❌ Event not found.")
        return

    title, score, ig, xlink = row

    msg = (
        f"🎪 *{title}*\n"
        f"⭐ Publicity Score: *{score}*\n\n"
        f"Use the buttons below to visit the IG or X post.\n"
        f"Repost it any time you want to boost this event!"
    )

    keyboard = []
    if ig:
        keyboard.append([InlineKeyboardButton("📸 Instagram Post", url=ig)])
    if xlink:
        keyboard.append([InlineKeyboardButton("🐦 X Post", url=xlink)])

    # Back button
    keyboard.append([InlineKeyboardButton("⬅️ Back to Events", callback_data="events_list")])

    await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def events_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Directly show events inline, used for initial events list and back button."""
    query = getattr(update, "callback_query", None)
    if query:
        await query.answer()
    await events(update, context)  # reuse your existing events() function


async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch user + all handles in one query
    cursor.execute("""
        SELECT 
            u.social_id,
            u.points,
            u.phone_number,
            s.platform,
            s.handle
        FROM users u
        LEFT JOIN social_handles s ON u.id = s.user_id
        WHERE u.telegram_id = %s
    """, (update.effective_user.id,))

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("⚠️ You don't have a profile yet. Use /start first.")
        return

    # Basic user info (shared across all rows)
    social_id = rows[0][0]
    points = rows[0][1]
    phone_number = rows[0][2] or "❌ Not set"

    # Extract social handles
    handles = {"x": None, "instagram": None, "tiktok": None}

    for _, _, _, platform, handle in rows:
        if platform in handles:
            handles[platform] = handle

    display_x = handles["x"] or "❌ Not set"
    display_ig = handles["instagram"] or "❌ Not set"
    display_tt = handles["tiktok"] or "❌ Not set"

    # Build the message
    msg = (
        f"👤 <b>Nelius Profile</b>\n"
        f"🪪 Social ID: <code>{social_id}</code>\n"
        f"🏆 Points: {points}\n"
        f"📞 Phone: {phone_number}\n\n"
        f"📱 <b>Social Handles</b>\n"
        f"🐦 X: {display_x}\n"
        f"📸 Instagram: {display_ig}\n"
        # f"🎵 TikTok: {display_tt}"
    )

    await update.message.reply_text(msg, parse_mode="HTML")


async def join_telegram_community(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🚀 Tap below to join Nelius Telegram community:\n\n{TELEGRAM_COMMUNITY_LINK}"
    )

async def join_whatsapp_community(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🚀 Tap below to join Nelius WhatsApp community:\n\n{WHATSAPP_COMMUNITY_LINK}"
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
    
    add_phone_handler = ConversationHandler(
    entry_points=[CommandHandler("addphone", add_or_update_phone)],
    states={
        PHONE_ENTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_phone)],
    },
    fallbacks=[CommandHandler("cancel", cancel)]
    )

    app.add_handler(add_phone_handler)

    # Basic commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("mypoints", mypoints))
    app.add_handler(CommandHandler("events", events))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("setx", setx))
    app.add_handler(CommandHandler("setig", setig))
    app.add_handler(CommandHandler("settiktok", settiktok))
    app.add_handler(CommandHandler("jointelegramcommunity", join_telegram_community))
    app.add_handler(CommandHandler("joinwhatsappcommunity", join_whatsapp_community))

    # Button interactions
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))
    
    # Dev commands (from nelius_dev.py)
    app.add_handler(CommandHandler("addevent", addevent))
    app.add_handler(CommandHandler("updateevent", updateevent))
    app.add_handler(CommandHandler("removeevent", removeevent))
    app.add_handler(CommandHandler("updatepub", updatepub))
    app.add_handler(CommandHandler("allocate", allocate))
    app.add_handler(CommandHandler("dump_db", dump_db))

    app.add_handler(CallbackQueryHandler(event_detail_callback, pattern=r"^event_\d+$"))
    app.add_handler(CallbackQueryHandler(events_list_callback, pattern=r"^events_list$"))

    print("Nelius DAO Bot is running...")

    await set_bot_commands(app)
    # asyncio.get_event_loop().run_until_complete(set_bot_commands(app))
    # app.run_polling()

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
