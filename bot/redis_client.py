import json
import os
import redis.asyncio as redis  # <-- Changed to async module
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL")

if not REDIS_URL:
    raise ValueError("Missing REDIS_URL in environment variables")

# Asynchronous connection pool
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

# ------------------------
# Helper Functions
# ------------------------

async def cache_user_profile(user_id: int, social_id: str, points: int):
    """Save user profile to Redis cache."""
    await redis_client.setex(
        f"user:{user_id}", 
        3600, 
        json.dumps({"social_id": social_id, "points": points})
    )

async def get_cached_user_profile(user_id: int):
    """Retrieve cached user profile, return None if not found."""
    cached = await redis_client.get(f"user:{user_id}")
    return json.loads(cached) if cached else None

async def cache_events_list(events: list):
    """Cache events list for 10 minutes."""
    await redis_client.setex("events:list", 600, json.dumps(events))

async def get_cached_events_list():
    """Retrieve cached events list."""
    cached = await redis_client.get("events:list")
    return json.loads(cached) if cached else None
