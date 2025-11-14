from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
import sqlite3
from settings import get_db_connection


async def setx(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Usage: /setx <your_X_handle>\nExample: /setx @timio"
        )
        return

    handle = context.args[0].strip()
    if not handle.startswith("@"):
        handle = "@" + handle

    conn = get_db_connection()
    cursor = conn.cursor()

    # Get or create user
    cursor.execute(
        "SELECT id FROM users WHERE telegram_id=%s",
        (update.effective_user.id,)
    )
    user_row = cursor.fetchone()
    if not user_row:
        await update.message.reply_text(
            "⚠️ You don't seem to be registered yet. Please use /start first."
        )
        conn.close()
        return
    user_id = user_row[0]

    # Upsert handle for platform 'x'
    cursor.execute("""
        INSERT INTO social_handles (user_id, platform, handle)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id, platform)
        DO UPDATE SET handle = EXCLUDED.handle
    """, (user_id, "x", handle))

    conn.commit()
    conn.close()

    await update.message.reply_text(f"✅ Your X handle has been saved as {handle}.")


async def setig(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Usage: /setig <your_Instagram_handle>\nExample: /setig @timio"
        )
        return

    handle = context.args[0].strip()
    if not handle.startswith("@"):
        handle = "@" + handle

    conn = get_db_connection()
    cursor = conn.cursor()

    # Get user row
    cursor.execute(
        "SELECT id FROM users WHERE telegram_id=%s",
        (update.effective_user.id,)
    )
    user_row = cursor.fetchone()

    if not user_row:
        await update.message.reply_text(
            "⚠️ You don't seem to be registered yet. Please use /start first."
        )
        conn.close()
        return

    user_id = user_row[0]

    # Upsert handle for platform 'ig'
    cursor.execute("""
        INSERT INTO social_handles (user_id, platform, handle)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id, platform)
        DO UPDATE SET handle = EXCLUDED.handle
    """, (user_id, "ig", handle))

    conn.commit()
    conn.close()

    await update.message.reply_text(f"✅ Your Instagram handle has been saved as {handle}.")


async def settiktok(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Usage: /settiktok <your_TikTok_handle>\nExample: /settiktok @timio"
        )
        return

    handle = context.args[0].strip()
    if not handle.startswith("@"):
        handle = "@" + handle

    conn = get_db_connection()
    cursor = conn.cursor()

    # Get user row
    cursor.execute(
        "SELECT id FROM users WHERE telegram_id=%s",
        (update.effective_user.id,)
    )
    user_row = cursor.fetchone()

    if not user_row:
        await update.message.reply_text(
            "⚠️ You don't seem to be registered yet. Please use /start first."
        )
        conn.close()
        return

    user_id = user_row[0]

    # Upsert handle for platform 'tiktok'
    cursor.execute("""
        INSERT INTO social_handles (user_id, platform, handle)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id, platform)
        DO UPDATE SET handle = EXCLUDED.handle
    """, (user_id, "tiktok", handle))

    conn.commit()
    conn.close()

    await update.message.reply_text(f"✅ Your TikTok handle has been saved as {handle}.")
