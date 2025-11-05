import json
from datetime import datetime
import redis
from .models import UserData

class RedisStore:
    def __init__(self, redis_url):
        try:
            self.redis_client = redis.from_url(redis_url)
            self.redis_client.ping()
            print(f"Successfully connected to Redis at {redis_url}")
        except redis.exceptions.ConnectionError as e:
            self.redis_client = None
            print(f"Could not connect to Redis at {redis_url}: {e}")

    def clear_all_user_data(self):
        if not self.redis_client:
            return
        keys = self.redis_client.keys("user_data:*")
        if keys:
            self.redis_client.delete(*keys)
            print(f"Cleared {len(keys)} user data entries from Redis.")

    def store_user_data(self, secret_str: str, user_data: UserData):
        """Stores user-specific configuration data in Redis."""
        if not self.redis_client: return
        self.redis_client.set(f"user_data:{secret_str}", user_data.model_dump_json())
        print(f"Stored UserData for secret_str: {secret_str}")

    def get_user_data(self, secret_str: str) -> UserData | None:
        """Retrieves user-specific configuration data from Redis."""
        if not self.redis_client: return None
        user_data_json = self.redis_client.get(f"user_data:{secret_str}")
        if user_data_json:
            return UserData.model_validate_json(user_data_json)
        return None

    def store_channels(self, channels: dict):
        """Stores M3U channel data in Redis."""
        if not self.redis_client: return
        pipeline = self.redis_client.pipeline()
        for tvg_id, channel in channels.items():
            pipeline.hset("channels", tvg_id, json.dumps(channel))
        pipeline.execute()
        print(f"Stored {len(channels)} channels in Redis.")

    def get_channel(self, tvg_id: str) -> str | None:
        """Retrieves a single channel by its tvg_id."""
        if not self.redis_client: return None
        channel_data = self.redis_client.hget("channels", tvg_id)
        if channel_data:
            return channel_data.decode('utf-8') # Return as string
        return None

    def get_all_channels(self) -> dict:
        """Retrieves all stored channels."""
        if not self.redis_client: return {}
        all_channels_data = self.redis_client.hgetall("channels")
        return {tvg_id.decode('utf-8'): channel_data.decode('utf-8') for tvg_id, channel_data in all_channels_data.items()}


    def clear_all_data(self):
        """Clears all M3U data from Redis."""
        if not self.redis_client: return
        self.redis_client.delete("channels")
        # Find all user_data keys and delete them
        for key in self.redis_client.scan_iter("user_data:*"):
            self.redis_client.delete(key)
        print("Cleared all M3U data from Redis.")

    def get_all_secret_strs(self) -> list[str]:
        """Retrieves all stored secret_str keys."""
        if not self.redis_client: return []
        keys = self.redis_client.keys("user_data:*")
        return [key.decode('utf-8').replace("user_data:", "") for key in keys]

    def store_processed_image(self, tvg_id: str, image_bytes: bytes):
        """Stores processed image bytes in Redis."""
        if not self.redis_client: return
        # Store with an expiration time (e.g., 7 days) to prevent Redis from filling up
        self.redis_client.setex(f"processed_image:{tvg_id}", 60 * 60 * 24 * 7, image_bytes)

    def get_processed_image(self, tvg_id: str) -> bytes | None:
        """Retrieves processed image bytes from Redis."""
        if not self.redis_client: return None
        image_data = self.redis_client.get(f"processed_image:{tvg_id}")
        return image_data


if __name__ == "__main__":
    # Example Usage
    redis_store = RedisStore("redis://localhost:6379/0")
    if redis_store.redis_client:
        # Clear existing data for a clean test
        redis_store.clear_all_data()

        # Sample M3U Channels
        sample_channels = [
            {"group_title": "News", "tvg_id": "CNN", "tvg_name": "CNN", "tvg_logo": "cnn.png", "url_tvg": "", "stream_url": "http://cnn.com/live"},
            {"group_title": "Sports", "tvg_id": "ESPN", "tvg_name": "ESPN", "tvg_logo": "espn.png", "url_tvg": "", "stream_url": "http://espn.com/live"},
        ]
        redis_store.store_channels(sample_channels)

        # Retrieve and print channels
        print("\nAll Channels:")
        for channel in redis_store.get_all_channels():
            print(channel)
        print("\nSpecific Channel (CNN):")
        print(redis_store.get_channel("CNN"))


    else:
        print("Redis client not initialized. Cannot run example usage.")
