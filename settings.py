import os
import psycopg
from dotenv import load_dotenv
import sqlite3

load_dotenv()

# --- Config ---
DATABASE_URL = os.getenv("DATABASE_URL")
DEV_IDS = [int(x) for x in os.getenv("DEV_IDS", "").split(",") if x]
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Telegram Bot Info
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_COMMUNITY_LINK = "https://t.me/+P9j1f85xo1ExZTk0"
WHATSAPP_COMMUNITY_LINK = "https://chat.whatsapp.com/LRyeXyFIkQcCTHSRzKed1x"

# Web Hook
WEBHOOK_URL = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/{TELEGRAM_BOT_TOKEN}"
PORT = int(os.getenv("PORT", 8080))

# --- SQL helper ---
def get_db_connection():
    if DATABASE_URL.startswith("postgres"):
        # psycopg3 connection (works with Supabase Session Pooler)
        return psycopg.connect(DATABASE_URL)

    elif DATABASE_URL.startswith("sqlite"):
        DB_PATH = DATABASE_URL.replace("sqlite:///", "")
        return sqlite3.connect(DB_PATH)

    else:
        raise ValueError("Unsupported DATABASE_URL format")
