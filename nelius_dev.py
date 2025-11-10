import os
import sqlite3
import redis
from dotenv import load_dotenv
from telegram.ext import ContextTypes
from telegram import Update
from settings import DATABASE_URL, DEV_IDS, REDIS_URL, get_db_connection
from bot_utils import export_table_to_csv

load_dotenv()
ADMIN_ID = int(os.getenv("ADMIN_IDS", "0"))

# --- Redis setup ---
r = redis.from_url(REDIS_URL, decode_responses=True)

# --- Decorator for dev-only commands ---
def dev_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id not in DEV_IDS:
            await update.message.reply_text("❌ You are not authorized for this command.")
            return
        return await func(update, context)
    return wrapper


# --- /addevent ---
@dev_only
async def addevent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    title = " ".join(context.args)
    if not title:
        await update.message.reply_text("Usage: /addevent <title>")
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO events (title) VALUES (?)", (title,))
    conn.commit()
    conn.close()

    # Cache event for quick future access
    event_id = cursor.lastrowid
    r.hset(f"event:{event_id}", mapping={"title": title, "publicity_score": 0})

    await update.message.reply_text(f"✅ Event '{title}' added (ID: {event_id}).")


# --- /updatepub ---
@dev_only
async def updatepub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /updatepub <event_id> <score>")
        return

    eid, score = context.args
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE events SET publicity_score=? WHERE id=?", (score, eid))
    conn.commit()
    conn.close()

    # Update cache
    if r.exists(f"event:{eid}"):
        r.hset(f"event:{eid}", "publicity_score", score)

    await update.message.reply_text(f"✅ Updated publicity score for event {eid} to {score}.")


# --- /allocate ---
@dev_only
async def allocate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /allocate <user_id> <points>")
        return

    uid, pts = context.args

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET points = points + ? WHERE social_id=?", (pts, uid))
    conn.commit()
    conn.close()

    # Update cache
    user_key = f"user:{uid}"
    if r.exists(user_key):
        r.hincrby(user_key, "points", int(pts))

    await update.message.reply_text(f"✅ Allocated {pts} points to user {uid}.")


@dev_only
async def removeevent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove an event by its ID."""
    if not context.args:
        await update.message.reply_text("Usage: /removeevent <event_id>")
        return

    eid = context.args[0]
    conn = get_db_connection()
    cursor = conn.cursor()

    # Check if event exists
    cursor.execute("SELECT title FROM events WHERE id=?", (eid,))
    row = cursor.fetchone()
    if not row:
        await update.message.reply_text(f"⚠️ No event found with ID {eid}.")
        conn.close()
        return

    title = row[0]
    cursor.execute("DELETE FROM events WHERE id=?", (eid,))
    conn.commit()
    conn.close()

    await update.message.reply_text(f"🗑️ Event '{title}' (ID: {eid}) removed successfully.")

@dev_only
async def dump_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Unauthorized.")
        return
    
    try:
        conn = get_db_connection()
        table_name = "users"  # replace with your table name
        buffer = export_table_to_csv(conn, table_name)

        await update.message.reply_document(
            document=buffer,
            filename=f"{table_name}_dump.csv",
            caption=f"Database dump of '{table_name}' table ✅"
        )
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")
