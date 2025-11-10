from itertools import product
import random
from redis_client import redis_client
from words import fruits, colors, adjectives

LIST_KEY = "nelius:available_ids"

def generate_social_ids():
    all_ids = [f"{adj}".capitalize()+f"{color}".capitalize()+f"{fruit}".capitalize() for adj, color, fruit in product(adjectives, colors, fruits)]
    random.shuffle(all_ids)
    print(f"Generated {len(all_ids)} unique Social IDs.")
    return all_ids

def load_to_redis():
    # Clear previous list to avoid duplicates
    redis_client.delete(LIST_KEY)
    all_ids = generate_social_ids()
    # Push all IDs into Redis list
    redis_client.lpush(LIST_KEY, *all_ids)
    print(f"Loaded {len(all_ids)} Social IDs into Redis list '{LIST_KEY}'.")

if __name__ == "__main__":
    load_to_redis()
