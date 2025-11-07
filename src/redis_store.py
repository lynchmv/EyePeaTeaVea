import json
from datetime import datetime, timedelta
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

    def get(self, key: str) -> bytes | None:
        """Retrieves a value from Redis by key."""
        if not self.redis_client: return None
        return self.redis_client.get(key)

    def set(self, key: str, value: bytes, expiration_time: int | None = None):
        """Stores a value in Redis with an optional expiration time."""
        if not self.redis_client: return
        self.redis_client.set(key, value, ex=expiration_time)

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

    def store_channel(self, tvg_id: str, channel_data: dict, expiration_time_seconds: int | None = None):
        """Stores a single channel or event in Redis with an optional expiration time."""
        if not self.redis_client: return
        key = f"channel:{tvg_id}"
        self.redis_client.set(key, json.dumps(channel_data), ex=expiration_time_seconds)
        print(f"Stored channel/event {tvg_id} with expiration {expiration_time_seconds}s.")

    def store_channels(self, channels: list[dict]):
        """Stores M3U channel data in Redis, handling events with expiration."""
        if not self.redis_client: return
        pipeline = self.redis_client.pipeline()
        for channel in channels:
            tvg_id = channel["tvg_id"]
            if channel.get("is_event") and channel.get("event_datetime_full"):
                try:
                    event_dt = datetime.strptime(channel["event_datetime_full"], "%Y-%m-%d %H:%M:%S")
                    # Add 4 hours to the event time for expiration
                    expiration_dt = event_dt + timedelta(hours=4)
                    now = datetime.now()
                    if expiration_dt > now:
                        expiration_time_seconds = int((expiration_dt - now).total_seconds())
                        key = f"channel:{tvg_id}"
                        pipeline.set(key, json.dumps(channel), ex=expiration_time_seconds)
                    else:
                        print(f"Event {tvg_id} is in the past, not storing with expiration.")
                except ValueError as e:
                    print(f"Error parsing event_datetime_full for {tvg_id}: {e}")
                    key = f"channel:{tvg_id}"
                    pipeline.set(key, json.dumps(channel)) # Store without expiration if date parsing fails or is in past
            else:
                key = f"channel:{tvg_id}"
                pipeline.set(key, json.dumps(channel)) # Store regular channels without expiration
        pipeline.execute()
        print(f"Stored {len(channels)} channels/events in Redis.")

    def get_channel(self, tvg_id: str) -> str | None:
        """Retrieves a single channel or event by its tvg_id."""
        if not self.redis_client: return None
        key = f"channel:{tvg_id}"
        channel_data = self.redis_client.get(key)
        if channel_data:
            return channel_data.decode('utf-8')
        return None

    def get_all_channels(self) -> dict:
        """Retrieves all stored channels and events."""
        if not self.redis_client: return {}
        all_keys = self.redis_client.keys("channel:*")
        all_channels_data = {}
        for key in all_keys:
            tvg_id = key.decode('utf-8').replace("channel:", "")
            channel_json = self.redis_client.get(key)
            if channel_json:
                all_channels_data[tvg_id] = channel_json.decode('utf-8')
        return all_channels_data

    def clear_all_data(self):
        """Clears all M3U data from Redis."""
        if not self.redis_client: return
        # Delete all channel:* keys
        for key in self.redis_client.scan_iter("channel:*"):
            self.redis_client.delete(key)
        # Find all user_data keys and delete them
        for key in self.redis_client.scan_iter("user_data:*"):
            self.redis_client.delete(key)
        print("Cleared all M3U data from Redis.")

    def get_all_secret_strs(self) -> list[str]:
        """Retrieves all stored secret_str keys."""
        if not self.redis_client: return []
        keys = self.redis_client.keys("user_data:*")
        return [key.decode('utf-8').replace("user_data:", "") for key in keys]

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
            {"group_title": "News", "tvg_id": "CNN", "tvg_name": "CNN", "tvg_logo": "cnn.png", "url_tvg": "", "stream_url": "http://cnn.com/live", "is_event": False},
            {"group_title": "Sports", "tvg_id": "ESPN", "tvg_name": "ESPN", "tvg_logo": "espn.png", "url_tvg": "", "stream_url": "http://espn.com/live", "is_event": False},
            {"group_title": "NFL", "tvg_id": "NFL_Event_1", "tvg_name": "11/06/2025 08:15:00 PM EST = Las Vegas Raiders @ Denver Broncos", "tvg_logo": "nfl.png", "url_tvg": "", "stream_url": "http://nfl.com/live", "is_event": True, "event_datetime_full": "2025-11-06 20:15:00"},
            {"group_title": "NBA", "tvg_id": "NBA_Event_1", "tvg_name": "11/07/2025 07:00:00 PM EST = Lakers vs Celtics", "tvg_logo": "nba.png", "url_tvg": "", "stream_url": "http://nba.com/live", "is_event": True, "event_datetime_full": "2025-11-07 19:00:00"},
        ]
        redis_store.store_channels(sample_channels)

        # Retrieve and print channels
        print("\nAll Channels:")
        for tvg_id, channel_data in redis_store.get_all_channels().items():
            print(f"{tvg_id}: {channel_data}")
        print("\nSpecific Channel (CNN):")
        print(redis_store.get_channel("CNN"))
        print("\nSpecific Event (NFL_Event_1):")
        print(redis_store.get_channel("NFL_Event_1"))

    else:
        print("Redis client not initialized. Cannot run example usage.")
