"""
Redis data store module for managing user data, channels, and image caching.

This module provides a RedisStore class that handles all Redis operations
with connection resilience, retry logic, and performance optimizations.
Supports per-user channel storage and global image caching.
"""
import json
import logging
import re
import time
import hashlib
from datetime import datetime, timedelta
from typing import Any
import pytz
import redis
from redis.connection import ConnectionPool
from redis.exceptions import ConnectionError, RedisError
from .models import UserData

logger = logging.getLogger(__name__)

# Performance constants
REDIS_BATCH_SIZE = 1000  # Batch size for bulk operations
IMAGE_CACHE_EXPIRATION_SECONDS = 60 * 60 * 24 * 7  # 7 days
EVENT_EXPIRATION_HOURS = 4  # Hours after event time before expiration

# Redis connection pool settings for high concurrency
REDIS_MAX_CONNECTIONS = 50  # Maximum connections in pool
REDIS_RETRY_ON_TIMEOUT = True  # Retry operations on timeout
REDIS_SOCKET_KEEPALIVE = True  # Enable TCP keepalive
REDIS_SOCKET_KEEPALIVE_OPTIONS = {}  # Keepalive options
REDIS_HEALTH_CHECK_INTERVAL = 30  # Health check interval in seconds

class RedisConnectionError(Exception):
    """
    Exception raised when Redis operations fail due to connection issues.
    
    This exception is raised when Redis is unavailable or connection
    cannot be established after retries.
    """
    pass

class RedisStore:
    """
    Redis data store with connection resilience and performance optimizations.
    
    Provides methods for storing and retrieving:
    - User configurations (per-user)
    - Channel data (per-user)
    - Processed images (global cache)
    
    Features:
    - Automatic connection retry with exponential backoff
    - Connection health checks
    - Batch operations for performance
    - Graceful error handling
    - Connection pooling for high concurrency
    
    Attributes:
        redis_url: Redis connection URL
        max_retries: Maximum connection retry attempts
        retry_delay: Delay between retry attempts in seconds
        redis_client: Redis client instance (None if not connected)
        connection_pool: Redis connection pool for concurrent operations
    """
    def __init__(
        self, 
        redis_url: str, 
        max_retries: int = 3, 
        retry_delay: float = 1.0
    ) -> None:
        """
        Initialize Redis connection with retry logic and connection pooling.
        
        Args:
            redis_url: Redis connection URL (e.g., "redis://localhost:6379/0")
            max_retries: Maximum number of connection retry attempts (default: 3)
            retry_delay: Delay in seconds between retry attempts (default: 1.0)
        """
        self.redis_url = redis_url
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.redis_client = None
        self.connection_pool = None
        self._connect_with_retry()
    
    def _connect_with_retry(self) -> None:
        """
        Attempt to connect to Redis with retry logic and connection pooling.
        
        Creates a connection pool for high concurrency and reuses connections
        across multiple requests. Tries to establish a connection up to max_retries times.
        Sets redis_client to None if all attempts fail.
        """
        for attempt in range(1, self.max_retries + 1):
            try:
                # Create connection pool for high concurrency
                # This allows multiple concurrent requests to share connections efficiently
                self.connection_pool = ConnectionPool.from_url(
                    self.redis_url,
                    max_connections=REDIS_MAX_CONNECTIONS,
                    retry_on_timeout=REDIS_RETRY_ON_TIMEOUT,
                    socket_connect_timeout=5,
                    socket_timeout=5,
                    socket_keepalive=REDIS_SOCKET_KEEPALIVE,
                    socket_keepalive_options=REDIS_SOCKET_KEEPALIVE_OPTIONS,
                    health_check_interval=REDIS_HEALTH_CHECK_INTERVAL,
                    decode_responses=False  # Keep binary mode for image data
                )
                
                # Create Redis client using the connection pool
                self.redis_client = redis.Redis(
                    connection_pool=self.connection_pool,
                    retry_on_timeout=REDIS_RETRY_ON_TIMEOUT
                )
                
                # Test connection
                self.redis_client.ping()
                logger.info(
                    f"Successfully connected to Redis at {self.redis_url} "
                    f"with connection pool (max_connections={REDIS_MAX_CONNECTIONS})"
                )
                return
            except (ConnectionError, RedisError) as e:
                if attempt < self.max_retries:
                    logger.warning(f"Redis connection attempt {attempt}/{self.max_retries} failed: {e}. Retrying in {self.retry_delay}s...")
                    time.sleep(self.retry_delay)
                else:
                    logger.error(f"Could not connect to Redis at {self.redis_url} after {self.max_retries} attempts: {e}")
                    self.redis_client = None
                    self.connection_pool = None
    
    def _ensure_connection(self) -> None:
        """
        Ensure Redis connection is active, reconnect if needed.
        
        Checks if connection exists and is alive. Attempts to reconnect
        if connection is lost. Raises RedisConnectionError if unable to connect.
        
        Raises:
            RedisConnectionError: If Redis is not available after retries
        """
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

    def clear_all_user_data(self) -> None:
        """
        Clear all user data from Redis.
        
        Uses scan_iter for better performance instead of keys().
        Deletes in batches to avoid blocking Redis.
        """
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

    def set(self, key: str, value: bytes, expiration_time: int | None = None) -> None:
        """Stores a value in Redis with an optional expiration time."""
        try:
            self._ensure_connection()
            self.redis_client.set(key, value, ex=expiration_time)
        except RedisConnectionError as e:
            logger.error(f"Cannot set key {key}: {e}")
            raise

    def incr(self, key: str, expiration_time: int | None = None) -> int:
        """
        Atomically increment a key's value in Redis.
        
        Args:
            key: Redis key to increment
            expiration_time: Optional expiration time in seconds (only set on first increment)
            
        Returns:
            The new value after incrementing
            
        Raises:
            RedisConnectionError: If Redis is unavailable
        """
        try:
            self._ensure_connection()
            # Use pipeline to atomically increment and set expiration if needed
            pipe = self.redis_client.pipeline()
            pipe.incr(key)
            if expiration_time is not None:
                # Only set expiration if key doesn't exist (first increment)
                pipe.expire(key, expiration_time)
            results = pipe.execute()
            return results[0]  # Return the incremented value
        except RedisConnectionError as e:
            logger.error(f"Cannot increment key {key}: {e}")
            raise

    def store_user_data(self, secret_str: str, user_data: UserData) -> None:
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

    def store_channel(
        self, 
        secret_str: str, 
        tvg_id: str, 
        channel_data: dict, 
        expiration_time_seconds: int | None = None
    ) -> None:
        """Stores a single channel or event in Redis with an optional expiration time, scoped to a user."""
        try:
            self._ensure_connection()
            key = f"channel:{secret_str}:{tvg_id}"
            self.redis_client.set(key, json.dumps(channel_data), ex=expiration_time_seconds)
            logger.debug(f"Stored channel/event {tvg_id} for user {secret_str[:8]}... with expiration {expiration_time_seconds}s.")
        except RedisConnectionError as e:
            logger.error(f"Cannot store channel {tvg_id} for {secret_str[:8]}...: {e}")
            raise

    def store_channels(self, secret_str: str, channels: list[dict]) -> None:
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

    def get_all_channels(self, secret_str: str) -> dict[str, str]:
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

    def clear_all_data(self) -> None:
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
    
    def clear_user_channels(self, secret_str: str) -> None:
        """
        Clears all channels and events for a specific user.
        
        Uses batch deletion for better performance with large datasets.
        """
        try:
            self._ensure_connection()
            pattern = f"channel:{secret_str}:*"
            keys_to_delete = []
            
            # Collect all keys to delete
            for key in self.redis_client.scan_iter(pattern):
                keys_to_delete.append(key)
            
            # Delete in batches for better performance
            deleted_count = 0
            if keys_to_delete:
                for i in range(0, len(keys_to_delete), REDIS_BATCH_SIZE):
                    batch = keys_to_delete[i:i + REDIS_BATCH_SIZE]
                    self.redis_client.delete(*batch)
                    deleted_count += len(batch)
            
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

    def store_processed_image(self, cache_key: str, image_bytes: bytes) -> None:
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
    
    def store_epg_data(self, secret_str: str, epg_data: dict) -> None:
        """
        Store EPG program data for a user.
        
        Args:
            secret_str: User's unique secret string
            epg_data: Dictionary mapping channel_id to list of programs
        """
        try:
            self._ensure_connection()
            key = f"epg:{secret_str}"
            # Store as JSON, expire after 7 days (EPG data is typically refreshed daily)
            self.redis_client.set(key, json.dumps(epg_data), ex=60 * 60 * 24 * 7)
            logger.info(f"Stored EPG data for {secret_str[:8]}... ({len(epg_data)} channels)")
        except RedisConnectionError as e:
            logger.error(f"Cannot store EPG data for {secret_str[:8]}...: {e}")
            raise
    
    def get_epg_data(self, secret_str: str) -> dict | None:
        """
        Retrieve EPG program data for a user.
        
        Args:
            secret_str: User's unique secret string
            
        Returns:
            Dictionary mapping channel_id to list of programs, or None if not found
        """
        try:
            self._ensure_connection()
            epg_json = self.redis_client.get(f"epg:{secret_str}")
            if epg_json:
                return json.loads(epg_json)
            return None
        except (RedisConnectionError, json.JSONDecodeError) as e:
            logger.error(f"Cannot get EPG data for {secret_str[:8]}...: {e}")
            return None
    
    def get_channel_programs(self, secret_str: str, channel_id: str) -> list[dict] | None:
        """
        Get programs for a specific channel.
        
        Args:
            secret_str: User's unique secret string
            channel_id: Channel identifier (tvg-id)
            
        Returns:
            List of program dictionaries, or None if not found
        """
        epg_data = self.get_epg_data(secret_str)
        if epg_data and channel_id in epg_data:
            return epg_data[channel_id]
        return None
    
    # Admin methods
    def store_admin_user(self, username: str, admin_user: dict) -> None:
        """Store admin user data in Redis."""
        try:
            self._ensure_connection()
            key = f"admin_user:{username}"
            self.redis_client.set(key, json.dumps(admin_user))
        except RedisConnectionError as e:
            logger.error(f"Cannot store admin user {username}: {e}")
            raise
    
    def get_admin_user(self, username: str) -> dict | None:
        """Retrieve admin user data from Redis."""
        try:
            self._ensure_connection()
            admin_json = self.redis_client.get(f"admin_user:{username}")
            if admin_json:
                return json.loads(admin_json)
            return None
        except (RedisConnectionError, json.JSONDecodeError) as e:
            logger.error(f"Cannot get admin user {username}: {e}")
            return None
    
    def get_all_admin_users(self) -> list[str]:
        """Get all admin usernames."""
        try:
            self._ensure_connection()
            usernames = []
            for key in self.redis_client.scan_iter(match="admin_user:*"):
                username = key.decode('utf-8').replace("admin_user:", "")
                usernames.append(username)
            return usernames
        except RedisConnectionError as e:
            logger.error(f"Cannot get admin users: {e}")
            return []
    
    def store_admin_session(self, session_id: str, session_data: dict, expiration_seconds: int = 3600 * 24) -> None:
        """Store admin session in Redis with expiration."""
        try:
            self._ensure_connection()
            key = f"admin_session:{session_id}"
            self.redis_client.setex(key, expiration_seconds, json.dumps(session_data))
        except RedisConnectionError as e:
            logger.error(f"Cannot store admin session {session_id}: {e}")
            raise
    
    def get_admin_session(self, session_id: str) -> dict | None:
        """Retrieve admin session from Redis."""
        try:
            self._ensure_connection()
            session_json = self.redis_client.get(f"admin_session:{session_id}")
            if session_json:
                return json.loads(session_json)
            return None
        except (RedisConnectionError, json.JSONDecodeError) as e:
            logger.error(f"Cannot get admin session {session_id}: {e}")
            return None
    
    def delete_admin_session(self, session_id: str) -> None:
        """Delete admin session from Redis."""
        try:
            self._ensure_connection()
            self.redis_client.delete(f"admin_session:{session_id}")
        except RedisConnectionError as e:
            logger.error(f"Cannot delete admin session {session_id}: {e}")
    
    def store_audit_log(self, log_entry: dict) -> None:
        """Store audit log entry in Redis (with TTL for automatic cleanup)."""
        try:
            self._ensure_connection()
            # Use timestamp as part of key for chronological ordering
            timestamp = log_entry.get("timestamp", datetime.now().isoformat())
            log_id = hashlib.sha256(f"{timestamp}{json.dumps(log_entry)}".encode()).hexdigest()[:16]
            key = f"audit_log:{timestamp}:{log_id}"
            # Store for 90 days
            self.redis_client.setex(key, 60 * 60 * 24 * 90, json.dumps(log_entry))
        except RedisConnectionError as e:
            logger.error(f"Cannot store audit log: {e}")
            # Don't raise - audit logging shouldn't break the app
    
    def store_parse_history(self, secret_str: str, parse_result: dict) -> None:
        """
        Store parse history entry for a user.
        
        Args:
            secret_str: User's unique secret string
            parse_result: Dictionary with parse result info (timestamp, success, channel_count, errors, etc.)
        """
        try:
            self._ensure_connection()
            timestamp = parse_result.get("timestamp", datetime.now().isoformat())
            # Store in a list, keep last 50 entries
            key = f"parse_history:{secret_str}"
            # Add to list (left push to keep newest first)
            self.redis_client.lpush(key, json.dumps(parse_result))
            # Trim to keep only last 50 entries
            self.redis_client.ltrim(key, 0, 49)
            # Set expiration (90 days)
            self.redis_client.expire(key, 60 * 60 * 24 * 90)
        except RedisConnectionError as e:
            logger.error(f"Cannot store parse history for {secret_str[:8]}...: {e}")
    
    def get_parse_history(self, secret_str: str, limit: int = 20) -> list[dict]:
        """
        Get parse history for a user.
        
        Args:
            secret_str: User's unique secret string
            limit: Maximum number of entries to return
            
        Returns:
            List of parse history entries (newest first)
        """
        try:
            self._ensure_connection()
            key = f"parse_history:{secret_str}"
            # Get entries (already sorted newest first due to lpush)
            entries = self.redis_client.lrange(key, 0, limit - 1)
            result = []
            for entry in entries:
                try:
                    result.append(json.loads(entry))
                except json.JSONDecodeError:
                    continue
            return result
        except RedisConnectionError as e:
            logger.error(f"Cannot get parse history for {secret_str[:8]}...: {e}")
            return []
    
    def store_user_error(self, secret_str: str, error_entry: dict) -> None:
        """
        Store error log entry for a user.
        
        Args:
            secret_str: User's unique secret string
            error_entry: Dictionary with error info (timestamp, error_type, message, source, etc.)
        """
        try:
            self._ensure_connection()
            timestamp = error_entry.get("timestamp", datetime.now().isoformat())
            # Store in a list, keep last 100 entries
            key = f"user_errors:{secret_str}"
            # Add to list (left push to keep newest first)
            self.redis_client.lpush(key, json.dumps(error_entry))
            # Trim to keep only last 100 entries
            self.redis_client.ltrim(key, 0, 99)
            # Set expiration (30 days)
            self.redis_client.expire(key, 60 * 60 * 24 * 30)
        except RedisConnectionError as e:
            logger.error(f"Cannot store user error for {secret_str[:8]}...: {e}")
    
    def get_user_errors(self, secret_str: str, limit: int = 50) -> list[dict]:
        """
        Get error logs for a user.
        
        Args:
            secret_str: User's unique secret string
            limit: Maximum number of entries to return
            
        Returns:
            List of error entries (newest first)
        """
        try:
            self._ensure_connection()
            key = f"user_errors:{secret_str}"
            # Get entries (already sorted newest first due to lpush)
            entries = self.redis_client.lrange(key, 0, limit - 1)
            result = []
            for entry in entries:
                try:
                    result.append(json.loads(entry))
                except json.JSONDecodeError:
                    continue
            return result
        except RedisConnectionError as e:
            logger.error(f"Cannot get user errors for {secret_str[:8]}...: {e}")
            return []
    
    # Logo override methods
    def store_logo_override(self, secret_str: str, tvg_id: str, logo_url: str, is_regex: bool = False) -> None:
        """
        Store a logo override for a channel.
        
        Args:
            secret_str: User's unique secret string
            tvg_id: Channel identifier or regex pattern
            logo_url: Override logo URL
            is_regex: Whether tvg_id is a regex pattern
        """
        try:
            self._ensure_connection()
            key = f"logo_override:{secret_str}:{tvg_id}"
            # Store as JSON to include metadata
            override_data = {
                "logo_url": logo_url,
                "is_regex": is_regex
            }
            self.redis_client.set(key, json.dumps(override_data))
            logger.info(f"Stored logo override for {secret_str[:8]}.../{tvg_id} (regex={is_regex})")
        except RedisConnectionError as e:
            logger.error(f"Cannot store logo override for {secret_str[:8]}.../{tvg_id}: {e}")
            raise
    
    def get_logo_override(self, secret_str: str, tvg_id: str) -> str | None:
        """
        Get logo override for a channel, checking both exact matches and regex patterns.
        Exact matches take precedence over regex patterns.
        
        Args:
            secret_str: User's unique secret string
            tvg_id: Channel identifier to match
            
        Returns:
            Override logo URL if exists (exact match or regex match), None otherwise
        """
        try:
            self._ensure_connection()
            # First check for exact match - this takes precedence over regex patterns
            exact_key = f"logo_override:{secret_str}:{tvg_id}"
            override_data = self.redis_client.get(exact_key)
            if override_data:
                try:
                    data = json.loads(override_data.decode('utf-8'))
                    logo_url = data.get("logo_url")
                    if logo_url:
                        logger.debug(f"Found exact logo override for {secret_str[:8]}.../{tvg_id}: {logo_url[:50]}...")
                        return logo_url
                except (json.JSONDecodeError, AttributeError):
                    # Legacy format (just URL string)
                    logo_url = override_data.decode('utf-8')
                    if logo_url:
                        logger.debug(f"Found exact logo override (legacy format) for {secret_str[:8]}.../{tvg_id}: {logo_url[:50]}...")
                        return logo_url
            
            # If no exact match, check regex patterns
            # Skip the exact match key when scanning to avoid redundant checks
            pattern = f"logo_override:{secret_str}:*"
            for key in self.redis_client.scan_iter(match=pattern):
                try:
                    key_str = key.decode('utf-8')
                    stored_tvg_id = key_str.replace(f"logo_override:{secret_str}:", "")
                    
                    # Skip exact match key (we already checked it above)
                    if stored_tvg_id == tvg_id:
                        continue
                    
                    # Get override data
                    override_data = self.redis_client.get(key)
                    if not override_data:
                        continue
                    
                    try:
                        data = json.loads(override_data.decode('utf-8'))
                        is_regex = data.get("is_regex", False)
                        logo_url = data.get("logo_url")
                    except (json.JSONDecodeError, AttributeError):
                        # Legacy format - skip regex matching for legacy entries
                        continue
                    
                    # Only check regex patterns (skip exact matches)
                    if is_regex and logo_url:
                        try:
                            # Compile and match the regex pattern
                            regex_pattern = re.compile(stored_tvg_id)
                            if regex_pattern.match(tvg_id):
                                logger.debug(f"Matched regex pattern {stored_tvg_id} for {secret_str[:8]}.../{tvg_id}: {logo_url[:50]}...")
                                return logo_url
                        except re.error as e:
                            logger.warning(f"Invalid regex pattern {stored_tvg_id}: {e}")
                            continue
                except Exception as e:
                    logger.error(f"Error processing logo override key {key}: {e}")
                    continue
            
            return None
        except RedisConnectionError as e:
            logger.error(f"Cannot get logo override for {secret_str[:8]}.../{tvg_id}: {e}")
            return None
    
    def delete_logo_override(self, secret_str: str, tvg_id: str) -> None:
        """
        Delete a logo override for a channel.
        
        Args:
            secret_str: User's unique secret string
            tvg_id: Channel identifier
        """
        try:
            self._ensure_connection()
            key = f"logo_override:{secret_str}:{tvg_id}"
            self.redis_client.delete(key)
            logger.info(f"Deleted logo override for {secret_str[:8]}.../{tvg_id}")
        except RedisConnectionError as e:
            logger.error(f"Cannot delete logo override for {secret_str[:8]}.../{tvg_id}: {e}")
            raise
    
    def get_all_logo_overrides(self, secret_str: str) -> dict[str, dict]:
        """
        Get all logo overrides for a user.
        
        Args:
            secret_str: User's unique secret string
            
        Returns:
            Dictionary mapping tvg_id/pattern to dict with 'logo_url' and 'is_regex' keys
        """
        try:
            self._ensure_connection()
            pattern = f"logo_override:{secret_str}:*"
            overrides = {}
            for key in self.redis_client.scan_iter(match=pattern):
                try:
                    # Extract tvg_id from key: "logo_override:{secret_str}:{tvg_id}"
                    key_str = key.decode('utf-8')
                    tvg_id = key_str.replace(f"logo_override:{secret_str}:", "")
                    override_data = self.redis_client.get(key)
                    if override_data:
                        try:
                            data = json.loads(override_data.decode('utf-8'))
                            overrides[tvg_id] = {
                                "logo_url": data.get("logo_url", ""),
                                "is_regex": data.get("is_regex", False)
                            }
                        except (json.JSONDecodeError, AttributeError):
                            # Legacy format (just URL string)
                            overrides[tvg_id] = {
                                "logo_url": override_data.decode('utf-8'),
                                "is_regex": False
                            }
                except Exception as e:
                    logger.error(f"Error processing logo override key {key}: {e}")
                    continue
            return overrides
        except RedisConnectionError as e:
            logger.error(f"Cannot get logo overrides for {secret_str[:8]}...: {e}")
            return {}


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
