import os
import redis
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL")

if not REDIS_URL:
    raise ValueError("Missing REDIS_URL in environment variables")

# Connection pool for thread/process safety
redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
