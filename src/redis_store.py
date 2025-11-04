import json
from datetime import datetime
import redis

class RedisStore:
    def __init__(self, redis_url):
        self.redis_client = redis.from_url(redis_url)

    def _connect_redis(self):
        """Establishes and returns a Redis client connection."""
        try:
            client = redis.from_url(self.redis_url)
            client.ping()
            print("Successfully connected to Redis!")
            return client
        except redis.exceptions.ConnectionError as e:
            print(f"Could not connect to Redis: {e}")
            return None

    def store_channels(self, channels: list[dict]):
        """Stores M3U channel data in Redis."""
        if not self.redis_client: return
        pipeline = self.redis_client.pipeline()
        for channel in channels:
            tvg_id = channel.get("tvg_id")
            if tvg_id:
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

    def store_programs(self, programs: list[dict]):
        """Stores EPG program data in Redis, indexed by channel and start time."""
        if not self.redis_client: return
        pipeline = self.redis_client.pipeline()
        for program in programs:
            channel_id = program.get("channel")
            start_time_str = program.get("start")
            if channel_id and start_time_str:
                # Convert start time to a sortable format (timestamp)
                # Assuming start_time_str is in 'YYYYMMDDHHMMSS +0000' format
                try:
                    # Remove the timezone offset for parsing, then assume UTC
                    dt_obj = datetime.strptime(start_time_str.split(' ')[0], '%Y%m%d%H%M%S')
                    timestamp = int(dt_obj.timestamp())
                    
                    # Store program in a sorted set for the channel, with timestamp as score
                    pipeline.zadd(f"programs:{channel_id}", {json.dumps(program): timestamp})
                except ValueError as e:
                    print(f"Error parsing program start time {start_time_str}: {e}")
        pipeline.execute()
        print(f"Stored {len(programs)} programs in Redis.")

    def get_programs_for_channel(self, channel_id: str, start_time: int = 0, end_time: int = 253402300799) -> list[dict]:
        """Retrieves programs for a given channel within a time range."""
        if not self.redis_client: return []
        # Use ZRANGEBYSCORE to get programs within the time range
        program_data = self.redis_client.zrangebyscore(f"programs:{channel_id}", start_time, end_time)
        return [json.loads(p_data) for p_data in program_data]

    def clear_all_data(self):
        """Clears all M3U and EPG data from Redis."""
        if not self.redis_client: return
        self.redis_client.delete("channels")
        # Find all program keys and delete them
        for key in self.redis_client.scan_iter("programs:*"):
            self.redis_client.delete(key)
        print("Cleared all M3U and EPG data from Redis.")

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

        # Sample EPG Programs
        # Note: The datetime format needs to match what parse_epg_content expects
        sample_programs = [
            {"start": "20251104100000 +0000", "stop": "20251104110000 +0000", "channel": "CNN", "title": "CNN News", "desc": "Daily news update", "category": "News"},
            {"start": "20251104110000 +0000", "stop": "20251104120000 +0000", "channel": "CNN", "title": "CNN Special", "desc": "Special report", "category": "News"},
            {"start": "20251104100000 +0000", "stop": "20251104120000 +0000", "channel": "ESPN", "title": "SportsCenter", "desc": "Latest sports news", "category": "Sports"},
        ]
        redis_store.store_programs(sample_programs)

        # Retrieve and print programs for a channel
        print("\nPrograms for CNN:")
        # Convert datetime to timestamp for querying
        start_ts = int(datetime(2025, 11, 4, 9, 0, 0).timestamp())
        end_ts = int(datetime(2025, 11, 4, 13, 0, 0).timestamp())
        for program in redis_store.get_programs_for_channel("CNN", start_ts, end_ts):
            print(program)

    else:
        print("Redis client not initialized. Cannot run example usage.")
