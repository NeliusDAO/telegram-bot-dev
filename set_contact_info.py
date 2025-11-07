import os
import random
import re
import sqlite3
import aiohttp
import redis.asyncio as aioredis
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler

load_dotenv()
# REDIS_URL = os.getenv("REDIS_URL")
# ASK_PHONE, ASK_OTP = range(2)
DB_PATH = "neliusdao.db"
OTP_ENTRY = range(1)

# # Redis connection
# redis_client = aioredis.from_url(os.getenv("REDIS_URL"),decode_responses=True)

# async def send_sms_otp(phone_number: str, otp: str):
#     api_key = os.getenv("TEXTBELT_API_KEY", "textbelt")
#     async with aiohttp.ClientSession() as session:
#         async with session.post("https://textbelt.com/text", data={
#             "phone": phone_number,
#             "message": f"Your Nelius DAO verification code is {otp}",
#             "key": api_key
#         }) as response:
#             return await response.json()

# # --- Step 1: User starts phone verification ---
# async def add_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     await update.message.reply_text("📱 Please enter your phone number (include country code, e.g. +234...):")
#     return OTP_ENTRY

# # --- Step 2: Send OTP and ask user to verify ---
# async def verify_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     phone_number = update.message.text.strip()
#     otp = str(random.randint(100000, 999999))

#     # Save OTP temporarily in Redis
#     await redis_client.setex(f"otp:{phone_number}", 300, otp)  # expires in 5 mins

#     result = await send_sms_otp(phone_number, otp)

#     if result.get("success"):
#         await update.message.reply_text("✅ OTP sent! Please enter the 6-digit code you received:")
#         context.user_data["pending_phone"] = phone_number
#         return "CONFIRM_OTP"
#     else:
#         await update.message.reply_text("❌ Failed to send OTP. Please try again later.")
#         return ConversationHandler.END

# # --- Step 3: Verify OTP ---
# async def confirm_otp(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     user_otp = update.message.text.strip()
#     phone_number = context.user_data.get("pending_phone")
#     saved_otp = await redis_client.get(f"otp:{phone_number}")

#     if saved_otp == user_otp:
#         # Save to DB
#         conn = sqlite3.connect(DB_PATH)
#         cursor = conn.cursor()
#         cursor.execute("UPDATE users SET phone_number=? WHERE telegram_id=?", (phone_number, update.effective_user.id))
#         conn.commit()
#         conn.close()

#         await redis_client.delete(f"otp:{phone_number}")
#         await update.message.reply_text("🎉 Phone number verified and saved successfully!")
#     else:
#         await update.message.reply_text("❌ Incorrect OTP or expired. Please try again with /addphone.")
#     return ConversationHandler.END

# # --- Cancel flow ---
# async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     await update.message.reply_text("🚫 Phone verification cancelled.")
#     return ConversationHandler.END

PHONE_ENTRY = range(1)

async def add_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
    "Coming soon in next update..."
    ,  parse_mode='HTML')
    # await update.message.reply_text(
    #     "📱 Please enter your phone number including country code but **without the + sign** (e.g. 234810...)."
    # ,  parse_mode='Markdown')
    return PHONE_ENTRY

async def save_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone_number = update.message.text.strip()

    # Automatically add "+" if user didn’t include it
    if not phone_number.startswith("+"):
        phone_number = f"+{phone_number}"

    # Validate after formatting
    if not phone_number[1:].isdigit() or len(phone_number) < 8:
        await update.message.reply_text(
            "❌ Please enter a valid phone number with country code (e.g. 234810...)."
        , parse_mode='Markdown')
        return PHONE_ENTRY

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET phone_number=? WHERE telegram_id=?",
        (phone_number, update.effective_user.id),
    )
    conn.commit()
    conn.close()

    await update.message.reply_text(f"✅ Your phone number {phone_number} has been saved for giveaways🎉!")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚫 Phone entry cancelled.")
    return ConversationHandler.END
