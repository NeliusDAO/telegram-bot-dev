import redis.asyncio as aioredis
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler
from settings import get_db_connection

load_dotenv()
PHONE_ENTRY = range(1)

# === ADD / UPDATE PHONE ===
async def add_or_update_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT phone_number FROM users WHERE telegram_id = %s",
        (user_id,)
    )
    record = cursor.fetchone()
    conn.close()

    if record and record[0]:
        msg = f"📞 You already have a phone number saved: *{record[0]}*.\n\nSend a *new number* (without +) to update it:"
    else:
        msg = "📱 Please enter your phone number including country code but *without the + sign* (e.g. 234810...)."

    await update.message.reply_text(msg, parse_mode='Markdown')
    return PHONE_ENTRY


async def save_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone_number = update.message.text.strip()

    # Automatically add "+" if user didn’t include it
    if not phone_number.startswith("+"):
        phone_number = f"+{phone_number}"

    # Validate after formatting
    if not phone_number[1:].isdigit() or len(phone_number) < 8:
        await update.message.reply_text(
            "❌ Please enter a valid phone number with country code (e.g. 234810...).",
            parse_mode='Markdown'
        )
        return PHONE_ENTRY

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET phone_number=%s WHERE telegram_id=%s",
        (phone_number, update.effective_user.id)
    )
    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"✅ Your phone number {phone_number} has been saved for giveaways🎉!"
    )
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚫 Phone entry cancelled.")
    return ConversationHandler.END
