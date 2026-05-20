from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes


async def setx(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /setx @yourhandle")
        return

    handle = args[0]
    if not handle.startswith("@"):
        handle = "@" + handle

    telegram_id = update.effective_user.id
    db_pool = context.bot_data['db_pool']

    async with db_pool.acquire() as conn:
        await conn.execute("""
            UPDATE users 
            SET handles = COALESCE(handles, '{}'::jsonb) || jsonb_build_object('x', $1::text)
            WHERE telegram_id = $2
        """, handle, telegram_id)

    await update.message.reply_text(f"✅ X handle updated to {handle}!")


async def setig(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /setig @yourhandle")
        return

    handle = args[0]
    if not handle.startswith("@"):
        handle = "@" + handle

    telegram_id = update.effective_user.id
    db_pool = context.bot_data['db_pool']

    async with db_pool.acquire() as conn:
        await conn.execute("""
            UPDATE users 
            SET handles = COALESCE(handles, '{}'::jsonb) || jsonb_build_object('instagram', $1::text)
            WHERE telegram_id = $2
        """, handle, telegram_id)

    await update.message.reply_text(f"✅ Instagram handle updated to {handle}!")


async def settiktok(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /settiktok @yourhandle")
        return

    handle = args[0]
    if not handle.startswith("@"):
        handle = "@" + handle

    telegram_id = update.effective_user.id
    db_pool = context.bot_data['db_pool']

    async with db_pool.acquire() as conn:
        await conn.execute("""
            UPDATE users 
            SET handles = COALESCE(handles, '{}'::jsonb) || jsonb_build_object('tiktok', $1::text)
            WHERE telegram_id = $2
        """, handle, telegram_id)

    await update.message.reply_text(f"✅ TikTok handle updated to {handle}!")