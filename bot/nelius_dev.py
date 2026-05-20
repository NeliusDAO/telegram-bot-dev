import os
import sqlite3
import json
from urllib.parse import urlparse
from dotenv import load_dotenv
from telegram.ext import ContextTypes
from telegram import Update, BotCommand, BotCommandScopeAllChatAdministrators, BotCommandScopeDefault, BotCommandScopeAllPrivateChats
from config.settings import BLEEPRS_API_KEY, DATABASE_URL, DEV_IDS, REDIS_URL
from bot.redis_client import redis_client as r
from bot.bot_utils import export_table_to_csv
from rewards.airtime_rewards import rewards

load_dotenv()
ADMIN_ID = int(os.getenv("ADMIN_IDS", "0"))

# --- Redis setup ---
# r = redis.from_url(REDIS_URL, decode_responses=True)


# --- Decorator for dev-only commands ---
def dev_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id not in DEV_IDS:
            await update.message.reply_text("❌ You are not authorized for this command.")
            return
        return await func(update, context)
    return wrapper

async def set_bot_commands(app, telegram_id=None):
    commands = [
        BotCommand("start", "Show main menu"),
        BotCommand("setx", "Set your X (Twitter) handle"),
        BotCommand("setig", "Set your Instagram handle"),
        BotCommand("settiktok", "Set your TikTok handle"),
        BotCommand("addphone", "Add your phone number"),
        BotCommand("jointelegramcommunity", "Join our Telegram community"),
        BotCommand("joinwhatsappcommunity", "Join our WhatsApp community"),
    ]
    await app.bot.set_my_commands(commands, scope=BotCommandScopeDefault())
    
    # For all private chats (so users only see these commands in DM with bot)
    await app.bot.set_my_commands(commands, scope=BotCommandScopeAllPrivateChats())
    await app.bot.set_my_commands(commands, scope=BotCommandScopeAllChatAdministrators())

async def force_refresh_bot_commands(app):
    # 1. Clear global commands
    await app.bot.delete_my_commands(scope=BotCommandScopeDefault())

    # 2. Clear private chat commands
    await app.bot.delete_my_commands(scope=BotCommandScopeAllPrivateChats())

    # 3. Clear chat admin commands
    await app.bot.delete_my_commands(scope=BotCommandScopeAllChatAdministrators())

    # 4. Re-set your commands again
    await set_bot_commands(app)

    print("Bot commands refreshed successfully!")


@dev_only
async def refresh_bot_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    await update.message.reply_text("🔄 Refreshing bot commands…")

    try:
        await force_refresh_bot_commands(context.application)

        await update.message.reply_text("✅ Bot commands refreshed for all users!")

    except Exception as e:
        await update.message.reply_text(f"❌ Failed to refresh commands:\n{e}")


# --- /addevent ---
@dev_only
async def addevent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args

    if not args:
        await update.message.reply_text(
            "Usage:\n/addevent <title> [link1] [link2] ...\n\n"
            "Example:\n/addevent The God of All Flesh https://instagram.com/post https://x.com/post https://bsky.app/post"
        )
        return

    # Separate links from title
    title_parts = []
    links_dict = {}

    for arg in args:
        if arg.startswith("http://") or arg.startswith("https://"):
            # Parse the URL dynamically
            parsed = urlparse(arg)
            domain = parsed.netloc.lower() # e.g., 'www.instagram.com'
            
            # Strip 'www.' if it exists
            if domain.startswith("www."):
                domain = domain[4:]
                
            # Extract the core platform name (everything before the first dot)
            # e.g., 'instagram.com' -> 'instagram', 'bsky.app' -> 'bsky'
            base_platform = domain.split('.')[0] if '.' in domain else "link"
            
            platform_name = base_platform

            # Just in case you add TWO links from the same platform (e.g., two X posts),
            # this prevents the second one from overwriting the first in the dictionary!
            counter = 1
            while platform_name in links_dict:
                platform_name = f"{base_platform}_{counter}"
                counter += 1
            
            links_dict[platform_name] = arg
        else:
            title_parts.append(arg)

    title = " ".join(title_parts)
    
    if not title:
        await update.message.reply_text("❌ Please provide a title for the event.")
        return

    # Convert the dictionary to a JSON string for asyncpg
    links_json = json.dumps(links_dict)

    db_pool = context.bot_data['db_pool']
    
    # 1. Acquire connection using async context manager
    async with db_pool.acquire() as conn:
        # 2. Insert title and the JSONB links object, returning the new ID
        event_id = await conn.fetchval(
            """
            INSERT INTO events (title, links)
            VALUES ($1, $2::jsonb)
            RETURNING id
            """,
            title, links_json
        )

    # Cache partial data for quick access
    await r.hset(f"event:{event_id}", mapping={
        "title": title,
        "publicity_score": 0
    })

    # Build a dynamic confirmation message
    msg_lines = [
        f"✅ Event added!",
        f"📌 ID: {event_id}",
        f"🎉 Title: {title}",
        f"🔗 Links attached: {len(links_dict)}"
    ]
    
    for plat, url in links_dict.items():
        # Capitalize the dynamic platform name so it looks nice (e.g., Bsky, X, Instagram)
        msg_lines.append(f"• {plat.capitalize()}: {url}")

    if not links_dict:
        msg_lines.append("• No links provided.")

    await update.message.reply_text("\n".join(msg_lines))

@dev_only
async def updateevent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args

    if not args:
        await update.message.reply_text(
            "Usage:\n/updateevent <event_id> [title] [platform_link] ...\n\n"
            "Example:\n/updateevent 5 The God of All Flesh https://instagram.com/post https://x.com/post"
        )
        return

    # Parse event_id
    try:
        event_id = int(args[0])
    except ValueError:
        await update.message.reply_text("⚠️ Event ID must be a number.")
        return

    # Separate title from links
    title_parts = []
    links_dict = {}

    for arg in args[1:]:
        if arg.startswith("http://") or arg.startswith("https://"):
            # Parse the URL dynamically
            parsed = urlparse(arg)
            domain = parsed.netloc.lower()
            
            if domain.startswith("www."):
                domain = domain[4:]
                
            base_platform = domain.split('.')[0] if '.' in domain else "link"
            platform_name = base_platform

            counter = 1
            while platform_name in links_dict:
                platform_name = f"{base_platform}_{counter}"
                counter += 1
            
            links_dict[platform_name] = arg
        else:
            title_parts.append(arg)

    title = " ".join(title_parts) if title_parts else None

    if not title and not links_dict:
        await update.message.reply_text("⚠️ Nothing to update. Please provide a new title or links.")
        return

    # Build dynamic SQL for the update
    updates = []
    values = []
    counter = 1 # Start at $1

    if title:
        updates.append(f"title = ${counter}")
        values.append(title)
        counter += 1
        
    if links_dict:
        # Convert dictionary to JSON string
        links_json = json.dumps(links_dict)
        # The || operator merges the new JSON into the existing JSON!
        # COALESCE ensures it doesn't fail if the existing links column is somehow NULL
        updates.append(f"links = COALESCE(links, '{{}}'::jsonb) || ${counter}::jsonb")
        values.append(links_json)
        counter += 1

    # Add the event_id as the final parameter for the WHERE clause
    values.append(event_id)
    sql = f"UPDATE events SET {', '.join(updates)} WHERE id = ${counter}"

    db_pool = context.bot_data['db_pool']
    async with db_pool.acquire() as conn:
        # Execute the update
        result = await conn.execute(sql, *values)
        
        # asyncpg execute returns a status string like "UPDATE 1". If it's "UPDATE 0", the ID doesn't exist.
        if result == "UPDATE 0":
            await update.message.reply_text(f"❌ Event ID {event_id} not found.")
            return

    # Update cache partially
    if title:
        # Assuming your redis_client is imported. If you used 'r' before, change it to redis_client
        await r.hset(f"event:{event_id}", mapping={"title": title})

    # Build response message
    updated_items = []
    if title:
        updated_items.append("📝 Title")
    if links_dict:
        # Show exactly which platforms were updated
        platforms_updated = ", ".join([p.capitalize() for p in links_dict.keys()])
        updated_items.append(f"🔗 Links ({platforms_updated})")

    await update.message.reply_text(
        f"✅ Event {event_id} successfully updated!\n"
        f"Updated: {', '.join(updated_items)}"
    )


@dev_only
async def updatepub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /updatepub <event_id> <score>")
        return

    # Grab explicitly by index to prevent unpacking crashes
    eid = int(context.args[0])
    score = int(context.args[1]) 
    db_pool = context.bot_data['db_pool']

    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE events SET publicity_score = $1 WHERE id = $2",
            score, eid
        )

    # Update cache (Add 'await' if you are using an async Redis client!)
    if await r.exists(f"event:{eid}"): 
        await r.hset(f"event:{eid}", "publicity_score", score)

    await update.message.reply_text(
        f"✅ Updated publicity score for event {eid} to {score}."
    )


@dev_only
async def allocate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /allocate <user_id> <points>")
        return

    uid, pts = context.args

    pts = int(context.args[1]) # Cast to int for asyncpg!

    db_pool = context.bot_data['db_pool']
    
    async with db_pool.acquire() as conn:
        # Use $1, $2
        await conn.execute(
            "UPDATE users SET points = points + $1 WHERE social_id = $2",
            pts, str(uid)
        )

    # Update cache
    user_key = f"user:{uid}"
    if await r.exists(user_key):
        await r.hincrby(user_key, "points", pts)

    await update.message.reply_text(f"✅ Allocated {pts} points to user {uid}.")


@dev_only
async def removeevent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /removeevent <event_id>")
        return

    eid = int(context.args[0]) # Cast to int for asyncpg!
    db_pool = context.bot_data['db_pool']

    async with db_pool.acquire() as conn:
        # fetchrow replaces fetchone()
        row = await conn.fetchrow("SELECT title FROM events WHERE id = $1", eid)

        if not row:
            await update.message.reply_text(f"⚠️ No event found with ID {eid}.")
            return

        # Access column by name instead of index!
        title = row['title'] 

        await conn.execute("DELETE FROM events WHERE id = $1", eid)

    await update.message.reply_text(
        f"🗑️ Event '{title}' (ID: {eid}) removed successfully."
    )


@dev_only
async def airtimereward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /airtimereward <phone_number> <amount>")
        return

    phone = context.args[0]
    amount = int(context.args[1])

    # Call the Bleeprs airtime client
    client = rewards.BleeprsAirtimeClient(BLEEPRS_API_KEY)
    result = client.purchase_airtime(phone, amount)

    if 'error' in result:
        await update.message.reply_text(f"Failed to share airtime: {result['error']}")
    else:
        await update.message.reply_text(f"Successfully shared ₦{amount} airtime to {phone}")


@dev_only
async def dump_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Unauthorized.")
        return

    if not context.args:
        await update.message.reply_text(
            "Usage: /dump_db <table_name>\n"
            "Available tables: users, events, social_handles"
        )
        return

    table_name = context.args[0].strip()

    # Validate table name to prevent SQL injection
    allowed_tables = {"users", "events", "social_handles"}
    if table_name not in allowed_tables:
        await update.message.reply_text(
            f"❌ Table '{table_name}' is not allowed.\n"
            f"Allowed tables: {', '.join(allowed_tables)}"
        )
        return

    db_pool = context.bot_data['db_pool']

    try:
        # Create an in-memory buffer to hold the CSV
        buffer = await export_table_to_csv(db_pool, table_name)

        await update.message.reply_document(
            document=buffer,
            filename=f"{table_name}_dump.csv",
            caption=f"✅ Database dump of '{table_name}' table"
        )
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

