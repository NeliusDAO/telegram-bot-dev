import os
import asyncpg
from dotenv import load_dotenv

load_dotenv()

# --- Config ---
DATABASE_URL = os.getenv("DATABASE_URL")
DEV_IDS = [int(x) for x in os.getenv("DEV_IDS", "").split(",") if x]
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Telegram Bot Info
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_COMMUNITY_LINK = os.getenv("TELEGRAM_COMMUNITY_LINK")
WHATSAPP_COMMUNITY_LINK = os.getenv("WHATSAPP_COMMUNITY_LINK")

# Rewards
BLEEPRS_API_KEY = os.getenv("BLEEPRS_API_KEY")
PHONEVERIFY_API_KEY = os.getenv("PHONEVERIFY_API_KEY")

# Web Hook
WEBHOOK_URL = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/{TELEGRAM_BOT_TOKEN}"
PORT = int(os.getenv("PORT", 8080))


async def init_db_pool(db_pool):
    """Run this exactly once when your app/bot starts to create tables."""
    # Note: We now pass db_pool in as an argument!
    async with db_pool.acquire() as conn:
        # Put your table creation queries here, for example:
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT UNIQUE,
            social_id TEXT UNIQUE,
            phone_number TEXT,
            points INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            handles JSONB  -- New column to store all social media handles in a single JSONB field
        );

        CREATE TABLE IF NOT EXISTS events (
            id SERIAL PRIMARY KEY,
            title TEXT,
            links JSONB,  -- Store all links in a JSONB column for flexibility
            publicity_score INTEGER DEFAULT 0
        );
        """)
        print("✅ Database tables verified/initialized.")

async def close_db_pool(db_pool):
    """Run this when your app shuts down."""
    if db_pool:
        await db_pool.close()

# --- How you use it in your code ---
async def get_user(user_id, db_pool):
    # Borrow a connection from the pool using the 'async with' context manager
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
        return row
