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

# Global variable to hold the pool
db_pool = None

async def init_db_pool():
    """Run this exactly once when your app/bot starts."""
    global db_pool
    if DATABASE_URL.startswith("postgres"):
        db_pool = await asyncpg.create_pool(DATABASE_URL)
    else:
        raise ValueError("This setup requires a PostgreSQL database.")

async def close_db_pool():
    """Run this when your app shuts down."""
    global db_pool
    if db_pool:
        await db_pool.close()

# --- How you use it in your code ---
async def get_user(user_id):
    # Borrow a connection from the pool using the 'async with' context manager
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
        return row
