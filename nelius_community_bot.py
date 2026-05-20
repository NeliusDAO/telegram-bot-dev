import asyncio
import asyncpg
import os
import json
from dotenv import load_dotenv
from telegram import (Update, KeyboardButton, ReplyKeyboardMarkup, 
                    ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup)
from telegram.ext import (Application, MessageHandler, CommandHandler, ConversationHandler,
                          CallbackQueryHandler, ContextTypes, filters)

from bot.redis_client import cache_user_profile, get_cached_user_profile, cache_events_list, get_cached_events_list
from config.settings import DATABASE_URL, TELEGRAM_BOT_TOKEN, TELEGRAM_COMMUNITY_LINK, WHATSAPP_COMMUNITY_LINK, WEBHOOK_URL, PORT, init_db_pool, close_db_pool
from bot.generate_and_load_ids import load_to_redis  # import your Social ID loader
from bot.variables import emoji_map

from bot.onboarding import (start_onboarding, PHONE_ENTRY, X_ENTRY, IG_ENTRY, TIKTOK_ENTRY, MAIN_MENU,
                        save_phone_onboarding, save_x_handle, save_ig_handle, finish_onboarding, cancel_onboarding)  # import onboarding handlers
from bot.assign_social_id import assign_social_id  # import your Social ID assignment function
from bot.nelius_dev import (set_bot_commands, refresh_bot_commands, addevent, updateevent, removeevent,
                        updatepub, allocate, dump_db, airtimereward)  # import dev-only commands
from bot.set_social_media_handles import setx, setig, settiktok  # import social media handle setter
from bot.set_contact_info import PHONE_NUMBER, add_or_update_phone, save_phone, cancel # import phone number handlers

load_dotenv()

# Connect to Redis
# redis_client = redis.from_url(REDIS_URL, decode_responses=True)


async def init_db(db_pool):
    """Creates the database tables if they do not exist."""
    async with db_pool.acquire() as conn:
        # asyncpg can execute multiple statements in a single block!
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT UNIQUE,
            social_id TEXT UNIQUE,
            phone_number TEXT,
            points INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            handles JSONB  -- New column to store all social media handles in a single JSONB field
        );

        CREATE TABLE IF NOT EXISTS events (
            id SERIAL PRIMARY KEY,
            title TEXT,
            links JSONB,  -- Store all links in a JSONB column for flexibility
            publicity_score INTEGER DEFAULT 0
        );
        
        CREATE TABLE IF NOT EXISTS social_handles (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            social_id TEXT REFERENCES users(social_id) ON DELETE CASCADE,
            platform TEXT NOT NULL,
            handle TEXT,
            UNIQUE(user_id, platform)
        );
        """)
        print("✅ Database tables verified/created.")

# ------------------------
# Telegram Bot Commands
# ------------------------

# MAIN_MENU = ReplyKeyboardMarkup(
#     [
#         ["🪪 My ID","🏆 My Points"],
#         ["🎉 Events","👤 My Profile"],
#     ],
#     resize_keyboard=True,
#     one_time_keyboard=False,
#     is_persistent=True
# )


# async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     user_id = update.effective_user.id
#     conn = get_db_connection()
#     cursor = conn.cursor()

#     cursor.execute(
#         "SELECT social_id, points FROM users WHERE telegram_id=%s",
#         (user_id,)
#     )
#     row = cursor.fetchone()

#     if not row:
#         social_id = assign_social_id(user_id)
#         cursor.execute(
#             "INSERT INTO users (telegram_id, social_id) VALUES (%s, %s)",
#             (user_id, social_id)
#         )
#         conn.commit()
#         points = 0
#         msg = f"👋 Welcome to Nelius DAO!\nYour Social ID: {social_id}"
#     else:
#         social_id, points = row
#         msg = f"👋 Welcome back!\nYour Social ID: {social_id}\n🏆 Points: {points}"

#     conn.close()

#     cache_user_profile(user_id, social_id, points)
#     await update.message.reply_text(msg, reply_markup=MAIN_MENU)


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Reminder: if get_cached_user_profile is an async Redis call, make sure to add 'await'
    profile = await get_cached_user_profile(user_id) 
    
    if not profile:
        db_pool = context.bot_data['db_pool']
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT social_id, points FROM users WHERE telegram_id = $1", 
                user_id
            )
            
        if not row:
            await update.message.reply_text("⚠️ You are not registered yet. Use /start to join Nelius.")
            return
            
        # Access by column name from the asyncpg Record object
        social_id = row['social_id']
        points = row['points']
        
        await cache_user_profile(user_id, social_id, points)
    else:
        social_id = profile["social_id"]

    await update.message.reply_text(f"🪪 Your Nelius Social ID: {social_id}")


async def mypoints(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Reminder: if get_cached_user_profile is an async Redis call, make sure to add 'await'
    profile = await get_cached_user_profile(user_id)

    if not profile:
        db_pool = context.bot_data['db_pool']
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT social_id, points FROM users WHERE telegram_id = $1", 
                user_id
            )
            
        if not row:
            await update.message.reply_text("⚠️ You are not registered yet. Use /start to join Nelius.")
            return
            
        # Access by column name
        social_id = row['social_id']
        points = row['points']
        
        await cache_user_profile(user_id, social_id, points)
    else:
        points = profile["points"]

    await update.message.reply_text(f"🏆 Your Nelius Points: {points}")


async def events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Reminder: if get_cached_events_list is an async Redis call, make sure to add 'await'
    events_data = await get_cached_events_list()

    if not events_data:
        db_pool = context.bot_data['db_pool']
        
        async with db_pool.acquire() as conn:
            # fetch() replaces fetchall() and returns a list of Record objects
            rows = await conn.fetch(
                "SELECT id, title, publicity_score FROM events ORDER BY id DESC"
            )

        # Build the list by accessing the Record dictionary keys
        events_data = [
            {"id": row['id'], "title": row['title'], "score": row['publicity_score']} for row in rows
        ]
        
        # 🔥 Sort by score (highest first)
        events_data.sort(key=lambda x: x["score"], reverse=True)

        await cache_events_list(events_data)

    else:
        # If cached, also ensure sorted
        events_data = sorted(events_data, key=lambda x: x["score"], reverse=True)

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
    db_pool = context.bot_data['db_pool']

    # Fetch event info using the new 'links' JSONB column
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT title, publicity_score, links FROM events WHERE id = $1",
            event_id
        )

    if not row:
        await query.edit_message_text("❌ Event not found.")
        return

    # Extract explicitly by column name
    title = row['title']
    score = row['publicity_score']
    
    # asyncpg returns JSONB as a string by default, so we parse it back into a dictionary
    raw_links = row['links']
    links_dict = json.loads(raw_links) if raw_links else {}

    # Update the message text to be platform-agnostic
    msg = (
        f"🎪 *{title}*\n"
        f"⭐ Publicity Score: *{score}*\n\n"
        f"Use the buttons below to visit the event posts.\n"
        f"Repost them any time you want to boost this event!"
    )

    keyboard = []
    
    # A handy map to give popular platforms their recognizable emojis
    emoji_map = {
        "instagram": "📸",
        "x": "🐦",
        "tiktok": "🎵",
        "youtube": "▶️",
        "linkedin": "💼",
        "facebook": "📘"
    }

    # Dynamically generate a button for every link in the database!
    for platform, url in links_dict.items():
        # Get the emoji if we know it, otherwise use a generic link emoji
        emoji = emoji_map.get(platform.lower(), "🔗")
        btn_text = f"{emoji} {platform.capitalize()} Post"
        
        keyboard.append([InlineKeyboardButton(btn_text, url=url)])

    # Back button
    keyboard.append([InlineKeyboardButton("⬅️ Back to Events", callback_data="events_list")])

    await query.edit_message_text(
        msg, 
        parse_mode="Markdown", 
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def events_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Directly show events inline, used for initial events list and back button."""
    query = getattr(update, "callback_query", None)
    if query:
        await query.answer()
    
    # This just calls your already-refactored events() function!
    await events(update, context)


async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    db_pool = context.bot_data['db_pool']

    # Fetch all user data in one clean, fast query (no JOINs needed!)
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT social_id, points, phone_number, handles
            FROM users
            WHERE telegram_id = $1
        """, telegram_id)

    if not row:
        await update.message.reply_text("⚠️ You don't have a profile yet. Use /start first.")
        return

    # Extract basic info
    social_id = row['social_id']
    points = row['points']
    phone_number = row['phone_number'] or "❌ Not set"

    # Extract handles safely from the JSONB column
    raw_handles = row['handles']
    handles_dict = json.loads(raw_handles) if raw_handles else {}

    # Build the message dynamically
    msg_lines = [
        f"👤 <b>Nelius Profile</b>",
        f"🪪 Social ID: <code>{social_id}</code>",
        f"🏆 Points: {points}",
        f"📞 Phone: {phone_number}",
        "",
        f"📱 <b>Social Handles</b>"
    ]

    # Dynamically generate handle lines based on whatever is saved
    if not handles_dict:
        msg_lines.append("❌ No handles set yet.")
    else:
        for platform, handle in handles_dict.items():
            emoji = emoji_map.get(platform.lower(), "🔗")
            msg_lines.append(f"{emoji} {platform.capitalize()}: {handle}")

    # Join the lines with line breaks and send
    await update.message.reply_text("\n".join(msg_lines), parse_mode="HTML")


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
# Startup & Shutdown Hooks
# ------------------------
async def post_init(application: Application):
    """Runs automatically when the bot starts."""
    # 1. Preload Redis IDs inside the bot's native event loop
    await load_to_redis()

    # 2. Create the asyncpg connection pool
    application.bot_data['db_pool'] = await asyncpg.create_pool(DATABASE_URL)
    print("✅ Database pool created.")
    
    # 3. Initialize tables using the pool we just created!
    await init_db_pool(application.bot_data['db_pool'])
    
    # 4. Set bot commands
    await set_bot_commands(application)
    print("✅ Bot commands registered.")

async def post_shutdown(application: Application):
    """Runs automatically when the bot is stopped (Ctrl+C)."""
    # Cleanly close the database connections
    db_pool = application.bot_data.get('db_pool')
    if db_pool:
        await db_pool.close()
        print("🛑 Database pool closed.")


# ------------------------
# Main Entry Point Locally (for development/testing)
# ------------------------
# async def main():
#     # 1. Start external services natively inside the main loop
#     await load_to_redis()
#     db_pool = await asyncpg.create_pool(DATABASE_URL)
#     await init_db(db_pool)

#     # 2. Build the Application
#     app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
#     # Store the db_pool so your handlers can access it!
#     app.bot_data['db_pool'] = db_pool

#     # 3. Add Handlers
#     onboarding_handler = ConversationHandler(
#         entry_points=[CommandHandler("start", start_onboarding)],
#         states={
#             PHONE_ENTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_phone_onboarding)],
#             X_ENTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_x_handle)],
#             IG_ENTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_ig_handle)],
#             TIKTOK_ENTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, finish_onboarding)],
#         },
#         fallbacks=[CommandHandler("cancel", cancel_onboarding)]
#     )
    
#     add_phone_handler = ConversationHandler(
#         entry_points=[CommandHandler("addphone", add_or_update_phone)],
#         states={
#             PHONE_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_phone)],
#         },
#         fallbacks=[CommandHandler("cancel", cancel)]
#     )

#     app.add_handler(onboarding_handler)
#     app.add_handler(add_phone_handler)

#     # Basic commands
#     app.add_handler(CommandHandler("start", start_onboarding))
#     app.add_handler(CommandHandler("myid", myid))
#     app.add_handler(CommandHandler("mypoints", mypoints))
#     app.add_handler(CommandHandler("events", events))
#     app.add_handler(CommandHandler("profile", profile))
#     app.add_handler(CommandHandler("setx", setx))
#     app.add_handler(CommandHandler("setig", setig))
#     app.add_handler(CommandHandler("settiktok", settiktok))
#     app.add_handler(CommandHandler("jointelegramcommunity", join_telegram_community))
#     app.add_handler(CommandHandler("joinwhatsappcommunity", join_whatsapp_community))

#     # Button interactions
#     app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))
    
#     # Dev commands
#     app.add_handler(CommandHandler("addevent", addevent))
#     app.add_handler(CommandHandler("updateevent", updateevent))
#     app.add_handler(CommandHandler("removeevent", removeevent))
#     app.add_handler(CommandHandler("updatepub", updatepub))
#     app.add_handler(CommandHandler("allocate", allocate))
#     app.add_handler(CommandHandler("refreshbotcommands", refresh_bot_commands))
#     app.add_handler(CommandHandler("dump_db", dump_db))
#     app.add_handler(CommandHandler("airtimereward", airtimereward))

#     app.add_handler(CallbackQueryHandler(event_detail_callback, pattern=r"^event_\d+$"))
#     app.add_handler(CallbackQueryHandler(events_list_callback, pattern=r"^events_list$"))

#     # 4. Set bot commands natively (no need given it is set in post_init)
#    # await set_bot_commands(app)

#     # 5. MANUALLY START THE BOT (Replaces app.run_polling())
#     await app.initialize()
#     await app.start()
#     await app.updater.start_polling()

#     print("🚀 Nelius DAO Bot is running... (Press Ctrl+C to stop)")

#     # 6. Keep the bot alive and handle graceful shutdown
#     stop_signal = asyncio.Event()
#     try:
#         await stop_signal.wait()  # Blocks here forever while the bot runs
#     except asyncio.CancelledError:
#         pass
#     finally:
#         print("\n🛑 Shutting down gracefully...")
#         await app.updater.stop()
#         await app.stop()
#         await app.shutdown()
#         await db_pool.close()
#         print("✅ Shutdown complete.")

# if __name__ == "__main__":
#     try:
#         # This is the ONLY event loop created in the entire application
#         asyncio.run(main())
#     except KeyboardInterrupt:
#         pass # Expected behavior when stopping the bot

# ------------------------
# Main Entry Point
# ------------------------
async def main():
    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    onboarding_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start_onboarding)],
        states={
            PHONE_ENTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_phone_onboarding)],
            X_ENTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_x_handle)],
            IG_ENTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_ig_handle)],
            TIKTOK_ENTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, finish_onboarding)],
        },
        fallbacks=[CommandHandler("cancel", cancel_onboarding)]
    )
    
    add_phone_handler = ConversationHandler(
        entry_points=[CommandHandler("addphone", add_or_update_phone)],
        states={
            PHONE_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_phone)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    app.add_handler(onboarding_handler)
    app.add_handler(add_phone_handler)

    # Basic commands
    app.add_handler(CommandHandler("start", start_onboarding))
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
    app.add_handler(MessageHandler(filters.Text(MAIN_MENU), handle_buttons))
    
    # Dev commands (from nelius_dev.py)
    app.add_handler(CommandHandler("addevent", addevent))
    app.add_handler(CommandHandler("updateevent", updateevent))
    app.add_handler(CommandHandler("removeevent", removeevent))
    app.add_handler(CommandHandler("updatepub", updatepub))
    app.add_handler(CommandHandler("allocate", allocate))
    app.add_handler(CommandHandler("refreshbotcommands", refresh_bot_commands))
    app.add_handler(CommandHandler("dump_db", dump_db))
    app.add_handler(CommandHandler("airtimereward", airtimereward))

    app.add_handler(CallbackQueryHandler(event_detail_callback, pattern=r"^event_\d+$"))
    app.add_handler(CallbackQueryHandler(events_list_callback, pattern=r"^events_list$"))

    print("🚀 Nelius DAO Bot is running...")

# === WEBHOOK SETUP ===
    # 1. We MUST grab the dynamic port Render provides, defaulting to 10000 if testing locally
    port = PORT or 10000
    
    # 2. Clean up the base URL so we don't accidentally get double slashes
    webhook_url = WEBHOOK_URL.rstrip("/")  # Remove trailing slash if present
    
    # Clear any old conflicting webhook settings
    await app.bot.delete_webhook()

    print(f"Starting server on dynamic Render port {port}...")

    await app.initialize()
    await app.start()
    
    # 3. start_webhook handles BOTH opening the server and telling Telegram the correct URL
    await app.updater.start_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=TELEGRAM_BOT_TOKEN,
        webhook_url=webhook_url, 
    )

    print(f"Webhook server running at {webhook_url}[:-15]... Waiting for updates...")

    # === SAFE RENDER SHUTDOWN ===
    stop_signal = asyncio.Event()
    try:
        await stop_signal.wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass  # Render triggered a restart
    finally:
        print("\n🛑 Shutting down gracefully...")
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        print("✅ Shutdown complete.")

if __name__ == "__main__":
    asyncio.run(main())