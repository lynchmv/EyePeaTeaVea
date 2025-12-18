import json
import logging
import time
from datetime import datetime, timedelta
import pytz
import redis
from redis.exceptions import ConnectionError, RedisError
from .models import UserData

logger = logging.getLogger(__name__)

# Performance constants
REDIS_BATCH_SIZE = 1000  # Batch size for bulk operations
IMAGE_CACHE_EXPIRATION_SECONDS = 60 * 60 * 24 * 7  # 7 days
EVENT_EXPIRATION_HOURS = 4  # Hours after event time before expiration

class RedisConnectionError(Exception):
    """Raised when Redis operations fail due to connection issues."""
    pass

class RedisStore:
    def __init__(self, redis_url, max_retries: int = 3, retry_delay: float = 1.0):
        """
        Initialize Redis connection with retry logic.
        
        Args:
            redis_url: Redis connection URL
            max_retries: Maximum number of connection retry attempts
            retry_delay: Delay in seconds between retry attempts
        """
        self.redis_url = redis_url
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.redis_client = None
        self._connect_with_retry()
    
    def _connect_with_retry(self):
        """Attempt to connect to Redis with retry logic."""
        for attempt in range(1, self.max_retries + 1):
            try:
                # Enable connection pooling for better performance
                self.redis_client = redis.from_url(
                    self.redis_url,
                    socket_connect_timeout=5,
                    socket_timeout=5,
                    socket_keepalive=True,
                    socket_keepalive_options={},
                    health_check_interval=30
                )
                self.redis_client.ping()
                logger.info(f"Successfully connected to Redis at {self.redis_url}")
                return
            except (ConnectionError, RedisError) as e:
                if attempt < self.max_retries:
                    logger.warning(f"Redis connection attempt {attempt}/{self.max_retries} failed: {e}. Retrying in {self.retry_delay}s...")
                    time.sleep(self.retry_delay)
                else:
                    logger.error(f"Could not connect to Redis at {self.redis_url} after {self.max_retries} attempts: {e}")
                    self.redis_client = None
    
    def _ensure_connection(self):
        """Ensure Redis connection is active, reconnect if needed."""
        if self.redis_client is None:
            self._connect_with_retry()
        
        if self.redis_client is None:
            raise RedisConnectionError(f"Redis is not available at {self.redis_url}")
        
        # Check if connection is still alive
        try:
            self.redis_client.ping()
        except (ConnectionError, RedisError) as e:
            logger.warning(f"Redis connection lost, attempting to reconnect: {e}")
            self._connect_with_retry()
            if self.redis_client is None:
                raise RedisConnectionError(f"Redis is not available at {self.redis_url}")
    
    def is_connected(self) -> bool:
        """Check if Redis connection is active."""
        if self.redis_client is None:
            return False
        try:
            self.redis_client.ping()
            return True
        except (ConnectionError, RedisError):
            return False

    def clear_all_user_data(self):
        """Clear all user data. Uses scan_iter for better performance."""
        try:
            self._ensure_connection()
            keys_to_delete = []
            # Use scan_iter instead of keys() for better performance
            for key in self.redis_client.scan_iter(match="user_data:*"):
                keys_to_delete.append(key)
            
            if keys_to_delete:
                # Delete in batches to avoid blocking Redis
                for i in range(0, len(keys_to_delete), REDIS_BATCH_SIZE):
                    batch = keys_to_delete[i:i + REDIS_BATCH_SIZE]
                    self.redis_client.delete(*batch)
                logger.info(f"Cleared {len(keys_to_delete)} user data entries from Redis.")
        except RedisConnectionError as e:
            logger.error(f"Cannot clear user data: {e}")
            raise

    def get(self, key: str) -> bytes | None:
        """Retrieves a value from Redis by key."""
        try:
            self._ensure_connection()
            return self.redis_client.get(key)
        except RedisConnectionError as e:
            logger.error(f"Cannot get key {key}: {e}")
            return None

    def set(self, key: str, value: bytes, expiration_time: int | None = None):
        """Stores a value in Redis with an optional expiration time."""
        try:
            self._ensure_connection()
            self.redis_client.set(key, value, ex=expiration_time)
        except RedisConnectionError as e:
            logger.error(f"Cannot set key {key}: {e}")
            raise

    def store_user_data(self, secret_str: str, user_data: UserData):
        """Stores user-specific configuration data in Redis."""
        try:
            self._ensure_connection()
            self.redis_client.set(f"user_data:{secret_str}", user_data.model_dump_json())
            logger.info(f"Stored UserData for secret_str: {secret_str[:8]}...")
        except RedisConnectionError as e:
            logger.error(f"Cannot store user data for {secret_str[:8]}...: {e}")
            raise

    def get_user_data(self, secret_str: str) -> UserData | None:
        """Retrieves user-specific configuration data from Redis."""
        try:
            self._ensure_connection()
            user_data_json = self.redis_client.get(f"user_data:{secret_str}")
            if user_data_json:
                return UserData.model_validate_json(user_data_json)
            return None
        except RedisConnectionError as e:
            logger.error(f"Cannot get user data for {secret_str[:8]}...: {e}")
            return None

    def store_channel(self, secret_str: str, tvg_id: str, channel_data: dict, expiration_time_seconds: int | None = None):
        """Stores a single channel or event in Redis with an optional expiration time, scoped to a user."""
        try:
            self._ensure_connection()
            key = f"channel:{secret_str}:{tvg_id}"
            self.redis_client.set(key, json.dumps(channel_data), ex=expiration_time_seconds)
            logger.debug(f"Stored channel/event {tvg_id} for user {secret_str[:8]}... with expiration {expiration_time_seconds}s.")
        except RedisConnectionError as e:
            logger.error(f"Cannot store channel {tvg_id} for {secret_str[:8]}...: {e}")
            raise

    def store_channels(self, secret_str: str, channels: list[dict]):
        """Stores M3U channel data in Redis for a specific user, handling events with expiration."""
        try:
            self._ensure_connection()
            pipeline = self.redis_client.pipeline()
            channels_stored = 0
            for channel in channels:
                tvg_id = channel["tvg_id"]
                if channel.get("is_event") and channel.get("event_datetime_full"):
                    try:
                        event_dt = datetime.strptime(channel["event_datetime_full"], "%Y-%m-%d %H:%M:%S")
                        event_dt = pytz.utc.localize(event_dt)
                        # Add expiration hours to the event time for expiration
                        expiration_dt = event_dt + timedelta(hours=EVENT_EXPIRATION_HOURS)
                        now = datetime.now(pytz.utc)
                        if expiration_dt > now:
                            expiration_time_seconds = int((expiration_dt - now).total_seconds())
                            key = f"channel:{secret_str}:{tvg_id}"
                            pipeline.set(key, json.dumps(channel), ex=expiration_time_seconds)
                            channels_stored += 1
                    except ValueError as e:
                        logger.error(f"Error parsing event_datetime_full for {tvg_id}: {e}")
                        # Do not store if date parsing fails
                else:
                    key = f"channel:{secret_str}:{tvg_id}"
                    pipeline.set(key, json.dumps(channel)) # Store regular channels without expiration
                    channels_stored += 1
            pipeline.execute()
            logger.info(f"Stored {channels_stored} channels/events in Redis for user {secret_str[:8]}...")
        except RedisConnectionError as e:
            logger.error(f"Cannot store channels for {secret_str[:8]}...: {e}")
            raise

    def get_channel(self, secret_str: str, tvg_id: str) -> str | None:
        """Retrieves a single channel or event by its tvg_id for a specific user."""
        try:
            self._ensure_connection()
            key = f"channel:{secret_str}:{tvg_id}"
            channel_data = self.redis_client.get(key)
            if channel_data:
                return channel_data.decode('utf-8')
            return None
        except RedisConnectionError as e:
            logger.error(f"Cannot get channel {tvg_id} for {secret_str[:8]}...: {e}")
            return None

    def get_all_channels(self, secret_str: str) -> dict:
        """
        Retrieves all stored channels and events for a specific user.
        Uses scan_iter for better performance with large datasets.
        """
        try:
            self._ensure_connection()
            pattern = f"channel:{secret_str}:*"
            all_channels_data = {}
            
            # Use scan_iter instead of keys() for better performance
            # scan_iter is non-blocking and works better with large datasets
            pipeline = self.redis_client.pipeline()
            keys_to_fetch = []
            
            # Collect all matching keys
            for key in self.redis_client.scan_iter(match=pattern):
                keys_to_fetch.append(key)
            
            # Batch fetch all channel data using pipeline
            if keys_to_fetch:
                for key in keys_to_fetch:
                    pipeline.get(key)
                
                results = pipeline.execute()
                
                # Process results
                for key, channel_json in zip(keys_to_fetch, results):
                    if channel_json:
                        # Extract tvg_id from key: "channel:{secret_str}:{tvg_id}"
                        key_str = key.decode('utf-8')
                        tvg_id = key_str.replace(f"channel:{secret_str}:", "")
                        all_channels_data[tvg_id] = channel_json.decode('utf-8')
            
            return all_channels_data
        except RedisConnectionError as e:
            logger.error(f"Cannot get all channels for {secret_str[:8]}...: {e}")
            return {}

    def clear_all_data(self):
        """Clears all M3U data from Redis. Uses batch deletion for better performance."""
        try:
            self._ensure_connection()
            # Delete all channel:* keys (both old format and new user-specific format)
            channel_keys = list(self.redis_client.scan_iter(match="channel:*"))
            for i in range(0, len(channel_keys), REDIS_BATCH_SIZE):
                batch = channel_keys[i:i + REDIS_BATCH_SIZE]
                self.redis_client.delete(*batch)
            
            # Delete all processed_image keys (both old format and new user-specific format)
            image_keys = list(self.redis_client.scan_iter(match="processed_image:*"))
            for i in range(0, len(image_keys), REDIS_BATCH_SIZE):
                batch = image_keys[i:i + REDIS_BATCH_SIZE]
                self.redis_client.delete(*batch)
            
            # Find all user_data keys and delete them
            user_data_keys = list(self.redis_client.scan_iter(match="user_data:*"))
            for i in range(0, len(user_data_keys), REDIS_BATCH_SIZE):
                batch = user_data_keys[i:i + REDIS_BATCH_SIZE]
                self.redis_client.delete(*batch)
            
            total_deleted = len(channel_keys) + len(image_keys) + len(user_data_keys)
            logger.info(f"Cleared all M3U data from Redis ({total_deleted} keys deleted).")
        except RedisConnectionError as e:
            logger.error(f"Cannot clear all data: {e}")
            raise
    
    def clear_user_channels(self, secret_str: str):
        """Clears all channels and events for a specific user."""
        try:
            self._ensure_connection()
            pattern = f"channel:{secret_str}:*"
            deleted_count = 0
            for key in self.redis_client.scan_iter(pattern):
                self.redis_client.delete(key)
                deleted_count += 1
            logger.info(f"Cleared {deleted_count} channels/events for user {secret_str[:8]}...")
        except RedisConnectionError as e:
            logger.error(f"Cannot clear channels for {secret_str[:8]}...: {e}")
            raise

    def get_all_secret_strs(self) -> list[str]:
        """
        Retrieves all stored secret_str keys.
        Uses scan_iter for better performance with large datasets.
        """
        try:
            self._ensure_connection()
            secret_strs = []
            # Use scan_iter instead of keys() for better performance
            for key in self.redis_client.scan_iter(match="user_data:*"):
                secret_str = key.decode('utf-8').replace("user_data:", "")
                secret_strs.append(secret_str)
            return secret_strs
        except RedisConnectionError as e:
            logger.error(f"Cannot get all secret_strs: {e}")
            return []

    def store_processed_image(self, cache_key: str, image_bytes: bytes):
        """Stores processed image bytes in Redis. Images are cached globally since the same channel logo produces the same processed image."""
        try:
            self._ensure_connection()
            # Store with an expiration time to prevent Redis from filling up
            key = f"processed_image:{cache_key}"
            self.redis_client.setex(key, IMAGE_CACHE_EXPIRATION_SECONDS, image_bytes)
        except RedisConnectionError as e:
            logger.error(f"Cannot store processed image {cache_key}: {e}")
            # Don't raise for image caching - it's not critical

    def get_processed_image(self, cache_key: str) -> bytes | None:
        """Retrieves processed image bytes from Redis. Images are cached globally since the same channel logo produces the same processed image."""
        try:
            self._ensure_connection()
            key = f"processed_image:{cache_key}"
            image_data = self.redis_client.get(key)
            return image_data
        except RedisConnectionError as e:
            logger.error(f"Cannot get processed image {cache_key}: {e}")
            return None


if __name__ == "__main__":
    # Example Usage
    from .utils import generate_secret_str
    redis_store = RedisStore("redis://localhost:6379/0")
    if redis_store.redis_client:
        # Clear existing data for a clean test
        redis_store.clear_all_data()

        # Generate a test secret_str
        test_secret_str = generate_secret_str()
        logger.info(f"Using test secret_str: {test_secret_str[:8]}...")

        # Sample M3U Channels
        sample_channels = [
            {"group_title": "News", "tvg_id": "CNN", "tvg_name": "CNN", "tvg_logo": "cnn.png", "url_tvg": "", "stream_url": "http://cnn.com/live", "is_event": False},
            {"group_title": "Sports", "tvg_id": "ESPN", "tvg_name": "ESPN", "tvg_logo": "espn.png", "url_tvg": "", "stream_url": "http://espn.com/live", "is_event": False},
            {"group_title": "NFL", "tvg_id": "NFL_Event_1", "tvg_name": "11/06/2025 08:15:00 PM EST = Las Vegas Raiders @ Denver Broncos", "tvg_logo": "nfl.png", "url_tvg": "", "stream_url": "http://nfl.com/live", "is_event": True, "event_datetime_full": "2025-11-06 20:15:00"},
            {"group_title": "NBA", "tvg_id": "NBA_Event_1", "tvg_name": "11/07/2025 07:00:00 PM EST = Lakers vs Celtics", "tvg_logo": "nba.png", "url_tvg": "", "stream_url": "http://nba.com/live", "is_event": True, "event_datetime_full": "2025-11-07 19:00:00"},
        ]
        redis_store.store_channels(test_secret_str, sample_channels)

        # Retrieve and log channels
        logger.info("\nAll Channels:")
        for tvg_id, channel_data in redis_store.get_all_channels(test_secret_str).items():
            logger.info(f"{tvg_id}: {channel_data}")
        logger.info("\nSpecific Channel (CNN):")
        logger.info(redis_store.get_channel(test_secret_str, "CNN"))
        logger.info("\nSpecific Event (NFL_Event_1):")
        logger.info(redis_store.get_channel(test_secret_str, "NFL_Event_1"))

    else:
        logger.error("Redis client not initialized. Cannot run example usage.")
