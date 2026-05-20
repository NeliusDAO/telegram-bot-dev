import asyncio
from itertools import product
import os
import sys
import random

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from bot.redis_client import redis_client
from bot.variables import fruits, colors, adjectives

LIST_KEY = "nelius:available_ids"

def generate_social_ids():
    """Generates strings in memory. No I/O, so it stays synchronous."""
    all_ids = [f"{adj}".capitalize()+f"{color}".capitalize()+f"{fruit}".capitalize() for adj, color, fruit in product(adjectives, colors, fruits)]
    random.shuffle(all_ids)
    print(f"Generated {len(all_ids)} unique Social IDs.")
    return all_ids

async def load_to_redis():
    """Interacts with Redis, so it must be async."""
    # Clear previous list to avoid duplicates
    await redis_client.delete(LIST_KEY)
    
    all_ids = generate_social_ids()
    
    # Push all IDs into Redis list
    await redis_client.lpush(LIST_KEY, *all_ids)
    print(f"Loaded {len(all_ids)} Social IDs into Redis list '{LIST_KEY}'.")

if __name__ == "__main__":
    # Use asyncio.run to execute the async function as a standalone script
    asyncio.run(load_to_redis())
