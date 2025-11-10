from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
import sqlite3
from settings import get_db_connection

async def setx(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /setx <your_X_handle>\nExample: /setx @rotimio")
        return

    handle = context.args[0].strip()
    if not handle.startswith("@"):
        handle = "@" + handle

    conn = get_db_connection()
    cursor = conn.cursor()

    # Get or create user
    cursor.execute("SELECT id FROM users WHERE telegram_id=?", (update.effective_user.id,))
    user_row = cursor.fetchone()
    if not user_row:
        await update.message.reply_text("⚠️ You don't seem to be registered yet. Please use /start first.")
        conn.close()
        return
    user_id = user_row[0]

    # Upsert (insert or update) handle for platform 'x'
    cursor.execute("""
        INSERT INTO social_handles (user_id, platform, handle)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id, platform)
        DO UPDATE SET handle=excluded.handle
    """, (user_id, "x", handle))
    conn.commit()
    conn.close()

    await update.message.reply_text(f"✅ Your X handle has been saved as {handle}.")
