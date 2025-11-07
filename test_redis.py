import os
import redis
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL")

r = redis.from_url(REDIS_URL, decode_responses=True)

try:
    r.ping()
    print("Connected to Redis locally!")
except redis.ConnectionError as e:
    print("Redis connection failed:", e)