import redis.asyncio as aioredis
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler

load_dotenv()
PHONE_NUMBER = range(1)

async def add_or_update_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Cast to str() if your telegram_id column is VARCHAR, or leave as int if it's BIGINT
    user_id = update.effective_user.id
    
    db_pool = context.bot_data['db_pool']

    async with db_pool.acquire() as conn:
        # fetchval() directly returns the single value of the first column (or None)
        # This completely replaces cursor.execute() + cursor.fetchone()[0]
        saved_phone = await conn.fetchval(
            "SELECT phone_number FROM users WHERE telegram_id = $1",
            user_id
        )

    if saved_phone:
        msg = f"📞 You already have a phone number saved: *{saved_phone}*.\n\nSend a *new number* (without +) to update it:"
    else:
        msg = "📱 Please enter your phone number including country code but *without the + sign* (e.g. 234810...)."

    await update.message.reply_text(msg, parse_mode='Markdown')
    return PHONE_NUMBER


async def save_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone_number = update.message.text.strip()
    user_id = update.effective_user.id

    # Automatically add "+" if user didn’t include it
    if not phone_number.startswith("+"):
        phone_number = f"+{phone_number}"

    # Validate after formatting
    if not phone_number[1:].isdigit() or len(phone_number) < 8:
        await update.message.reply_text(
            "❌ Please enter a valid phone number with country code (e.g. 234810...).",
            parse_mode='Markdown'
        )
        return PHONE_NUMBER

    db_pool = context.bot_data['db_pool']
    
    async with db_pool.acquire() as conn:
        # Replaced %s with $1, $2 and removed conn.commit()
        await conn.execute(
            "UPDATE users SET phone_number = $1 WHERE telegram_id = $2",
            phone_number, user_id
        )

    await update.message.reply_text(
        f"✅ Your phone number {phone_number} has been saved for giveaways🎉!"
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚫 Phone entry cancelled.")
    return ConversationHandler.END