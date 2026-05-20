import json
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ConversationHandler, 
    CommandHandler, 
    MessageHandler, 
    filters, 
    ContextTypes
)

from bot.redis_client import cache_user_profile
from bot.assign_social_id import assign_social_id

# Define conversation states
PHONE_ENTRY, X_ENTRY, IG_ENTRY, TIKTOK_ENTRY = range(4)

# Reusable skip keyboard for optional steps
SKIP_MARKUP = ReplyKeyboardMarkup([["Skip"]], one_time_keyboard=True, resize_keyboard=True)

MAIN_MENU = ReplyKeyboardMarkup(
    [
        ["🪪 My ID","🏆 My Points"],
        ["🎉 Events","👤 My Profile"],
    ],
    resize_keyboard=True,
    one_time_keyboard=False,
    is_persistent=True
)


async def start_onboarding(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point for /start."""
    user_id = update.effective_user.id # int8 / BIGINT
    db_pool = context.bot_data['db_pool']

    async with db_pool.acquire() as conn:
        # fetchrow returns a dictionary-like Record, or None
        row = await conn.fetchrow("SELECT social_id, points FROM users WHERE telegram_id=$1", user_id)

        if not row:
            # --- NEW USER FLOW ---
            social_id = await assign_social_id(user_id) # Assuming this is a sync function you defined
            
            await conn.execute(
                "INSERT INTO users (telegram_id, social_id) VALUES ($1, $2)",
                user_id, str(social_id)
            )
            
            # Initiate the step-by-step onboarding
            await update.message.reply_text(
                f"👋 Welcome to Nelius DAO!\nYour Social ID: {social_id}\n\n"
                "To get started, please reply with your phone number including country code but *without the + sign* (e.g. 234810...).",
                reply_markup=ReplyKeyboardRemove()
            )
            return PHONE_ENTRY

        else:
            # --- EXISTING USER FLOW ---
            # Access the row using dictionary keys
            social_id = row['social_id']
            points = row['points']
            
            # NOTE: If cache_user_profile uses async Redis, add an 'await' here!
            await cache_user_profile(user_id, social_id, points) 
            msg = f"👋 Welcome back!\nYour Social ID: {social_id}\n🏆 Points: {points}"
            
            await update.message.reply_text(msg, reply_markup=MAIN_MENU)
            return ConversationHandler.END


async def save_phone_onboarding(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save phone and ask for optional X handle."""
    phone = update.message.text.strip()
    user_id = update.effective_user.id
    db_pool = context.bot_data['db_pool']
    
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE users SET phone_number = $1 WHERE telegram_id = $2", phone, user_id)
    
    await update.message.reply_text(
        "✅ Phone saved!\n\n"
        "Next, please enter your X (Twitter) handle (e.g., @username).\nTap 'Skip' if you want to add it later.",
        reply_markup=SKIP_MARKUP
    )
    return X_ENTRY

async def save_x_handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save X handle into JSONB and ask for optional IG handle."""
    text = update.message.text.strip()
    telegram_id = update.effective_user.id
    db_pool = context.bot_data['db_pool']
    
    if text.lower() != "skip":
        if not text.startswith("@"):
            text = "@" + text
            
        async with db_pool.acquire() as conn:
            # Merge the new handle into the JSON object
            await conn.execute("""
                UPDATE users 
                SET handles = COALESCE(handles, '{}'::jsonb) || jsonb_build_object('x', $1::text)
                WHERE telegram_id = $2
            """, text, telegram_id)
    
    await update.message.reply_text(
        "✅ X handle saved!\n\n"
        "Please enter your Instagram handle (e.g., @username), or tap 'Skip' if you want to add it later.",
        reply_markup=SKIP_MARKUP
    )
    return IG_ENTRY


async def save_ig_handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save IG handle into JSONB and ask for optional TikTok handle."""
    text = update.message.text.strip()
    telegram_id = update.effective_user.id
    db_pool = context.bot_data['db_pool']
    
    if text.lower() != "skip":
        if not text.startswith("@"):
            text = "@" + text
            
        async with db_pool.acquire() as conn:
            await conn.execute("""
                UPDATE users 
                SET handles = COALESCE(handles, '{}'::jsonb) || jsonb_build_object('instagram', $1::text)
                WHERE telegram_id = $2
            """, text, telegram_id)
        
    await update.message.reply_text(
        "✅ Got it!\n\n"
        "Finally, enter your TikTok handle (e.g., @username), or tap 'Skip'.",
        reply_markup=SKIP_MARKUP
    )
    return TIKTOK_ENTRY


async def finish_onboarding(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save TikTok handle into JSONB, fetch final profile, and conclude onboarding."""
    text = update.message.text.strip()
    telegram_id = update.effective_user.id
    db_pool = context.bot_data['db_pool']
    
    async with db_pool.acquire() as conn:
        if text.lower() != "skip":
            if not text.startswith("@"):
                text = "@" + text
                
            await conn.execute("""
                UPDATE users 
                SET handles = COALESCE(handles, '{}'::jsonb) || jsonb_build_object('tiktok', $1::text)
                WHERE telegram_id = $2
            """, text, telegram_id)
            
        # Fetch the final profile data for Redis caching
        row = await conn.fetchrow(
            "SELECT social_id, points FROM users WHERE telegram_id = $1", 
            telegram_id
        )
        social_id = row['social_id'] if row else "unknown"
        points = row['points'] if row else 0

    # Cache the profile
    await cache_user_profile(telegram_id, social_id, points)
    
    await update.message.reply_text(
        "🎉 Setup complete! You are fully onboarded and ready to earn points.",
        reply_markup=MAIN_MENU 
    )
    return ConversationHandler.END


async def cancel_onboarding(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fallback if user cancels."""
    await update.message.reply_text(
        "Setup paused. You can use /start to resume later.", 
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END