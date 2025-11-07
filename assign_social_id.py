from redis_client import redis_client

LIST_KEY = "nelius:available_ids"
USER_KEY_PREFIX = "nelius:user:"

def assign_social_id(user_id: str):
    """
    Atomically assigns one Social ID to a user, ensuring uniqueness.
    """
    user_key = f"{USER_KEY_PREFIX}{user_id}"

    # If user already has one, return it
    existing = redis_client.get(user_key)
    if existing:
        return existing

    # Atomically pop from Redis list (safe for concurrent users)
    social_id = redis_client.rpop(LIST_KEY)

    if not social_id:
        raise Exception("No available Social IDs left!")

    # Save the mapping (optional: set TTL or persist)
    redis_client.set(user_key, social_id)

    print(f"Assigned '{social_id}' to user {user_id}")
    return social_id
