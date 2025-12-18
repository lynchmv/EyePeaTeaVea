import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import unittest
import os
import json
import redis
from datetime import datetime
from src.redis_store import RedisStore
from src.models import UserData
from src.utils import generate_secret_str

class TestRedisStore(unittest.TestCase):

    def setUp(self):
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0") # Use a different DB for testing
        self.redis_store = RedisStore(self.redis_url)
        self.redis_store.clear_all_data() # Clear data before each test

    def tearDown(self):
        self.redis_store.clear_all_data() # Clear data after each test

    def test_store_and_get_channel(self):
        secret_str = generate_secret_str()
        channel_data = {
            "group_title": "News",
            "tvg_id": "CNN",
            "tvg_name": "CNN",
            "tvg_logo": "cnn.png",
            "url_tvg": "",
            "stream_url": "http://cnn.com/live"
        }
        self.redis_store.store_channels(secret_str, [channel_data])
        retrieved_channel_json = self.redis_store.get_channel(secret_str, "CNN")
        self.assertIsNotNone(retrieved_channel_json)
        retrieved_channel = json.loads(retrieved_channel_json)
        self.assertEqual(retrieved_channel["tvg_id"], "CNN")
        self.assertEqual(retrieved_channel["stream_url"], "http://cnn.com/live")

    def test_get_all_channels(self):
        secret_str = generate_secret_str()
        channel_data_1 = {
            "group_title": "News",
            "tvg_id": "CNN",
            "tvg_name": "CNN",
            "tvg_logo": "cnn.png",
            "url_tvg": "",
            "stream_url": "http://cnn.com/live"
        }
        channel_data_2 = {
            "group_title": "Sports",
            "tvg_id": "ESPN",
            "tvg_name": "ESPN",
            "tvg_logo": "espn.png",
            "url_tvg": "",
            "stream_url": "http://espn.com/live"
        }
        self.redis_store.store_channels(secret_str, [
            channel_data_1,
            channel_data_2
        ])
        all_channels = self.redis_store.get_all_channels(secret_str)
        self.assertEqual(len(all_channels), 2)
        self.assertIn("CNN", all_channels)
        self.assertIn("ESPN", all_channels)

    def test_user_channel_isolation(self):
        """Test that channels from different users are isolated from each other."""
        secret_str_1 = generate_secret_str()
        secret_str_2 = generate_secret_str()
        
        channel_data_1 = {
            "group_title": "News",
            "tvg_id": "CNN",
            "tvg_name": "CNN",
            "tvg_logo": "cnn.png",
            "url_tvg": "",
            "stream_url": "http://cnn.com/live"
        }
        channel_data_2 = {
            "group_title": "Sports",
            "tvg_id": "ESPN",
            "tvg_name": "ESPN",
            "tvg_logo": "espn.png",
            "url_tvg": "",
            "stream_url": "http://espn.com/live"
        }
        
        # Store channels for user 1
        self.redis_store.store_channels(secret_str_1, [channel_data_1])
        # Store channels for user 2
        self.redis_store.store_channels(secret_str_2, [channel_data_2])
        
        # User 1 should only see their own channels
        user1_channels = self.redis_store.get_all_channels(secret_str_1)
        self.assertEqual(len(user1_channels), 1)
        self.assertIn("CNN", user1_channels)
        self.assertNotIn("ESPN", user1_channels)
        
        # User 2 should only see their own channels
        user2_channels = self.redis_store.get_all_channels(secret_str_2)
        self.assertEqual(len(user2_channels), 1)
        self.assertIn("ESPN", user2_channels)
        self.assertNotIn("CNN", user2_channels)
        
        # User 1 should not be able to access user 2's channels
        self.assertIsNone(self.redis_store.get_channel(secret_str_1, "ESPN"))
        # User 2 should not be able to access user 1's channels
        self.assertIsNone(self.redis_store.get_channel(secret_str_2, "CNN"))

    def test_clear_all_data(self):
        secret_str = generate_secret_str()
        channel_data = {
            "group_title": "News",
            "tvg_id": "CNN",
            "tvg_name": "CNN",
            "tvg_logo": "cnn.png",
            "url_tvg": "",
            "stream_url": "http://cnn.com/live"
        }
        self.redis_store.store_channels(secret_str, [channel_data])
        self.redis_store.clear_all_data()
        all_channels = self.redis_store.get_all_channels(secret_str)
        self.assertEqual(len(all_channels), 0)

    def test_store_and_get_user_data(self):
        secret_str = generate_secret_str()
        user_data = UserData(
            m3u_sources=["http://m3u.test/playlist.m3u"],
            parser_schedule_crontab="0 0 * * *",
            host_url="http://localhost:8020",
            addon_password="test_password"
        )
        self.redis_store.store_user_data(secret_str, user_data)
        retrieved_user_data = self.redis_store.get_user_data(secret_str)
        self.assertIsNotNone(retrieved_user_data)
        self.assertEqual(retrieved_user_data.m3u_sources, user_data.m3u_sources)
        self.assertEqual(retrieved_user_data.addon_password, user_data.addon_password)

    def test_get_all_secret_strs(self):
        secret_str_1 = generate_secret_str()
        user_data_1 = UserData(
            m3u_sources=["http://m3u1.test/playlist.m3u"],
            parser_schedule_crontab="0 0 * * *",
            host_url="http://localhost:8020"
        )
        self.redis_store.store_user_data(secret_str_1, user_data_1)

        secret_str_2 = generate_secret_str()
        user_data_2 = UserData(
            m3u_sources=["http://m3u2.test/playlist.m3u"],
            parser_schedule_crontab="0 0 * * *",
            host_url="http://localhost:8020"
        )
        self.redis_store.store_user_data(secret_str_2, user_data_2)

        all_secret_strs = self.redis_store.get_all_secret_strs()
        self.assertEqual(len(all_secret_strs), 2)
        self.assertIn(secret_str_1, all_secret_strs)
        self.assertIn(secret_str_2, all_secret_strs)

    def test_event_expiration(self):
        """Test that events are stored with expiration based on event_datetime_full."""
        import pytz
        from datetime import datetime, timedelta
        
        secret_str = generate_secret_str()
        
        # Create an event with a future datetime
        future_dt = datetime.now(pytz.utc) + timedelta(hours=2)
        event_data = {
            "group_title": "Sports",
            "tvg_id": "FutureEvent",
            "tvg_name": "Future Game",
            "tvg_logo": "sports.png",
            "url_tvg": "",
            "stream_url": "http://sports.com/live",
            "is_event": True,
            "event_datetime_full": future_dt.strftime("%Y-%m-%d %H:%M:%S")
        }
        
        self.redis_store.store_channels(secret_str, [event_data])
        
        # Verify event was stored
        retrieved_channel_json = self.redis_store.get_channel(secret_str, "FutureEvent")
        self.assertIsNotNone(retrieved_channel_json)
        
        # Verify TTL is set (should be approximately 4 hours after event time)
        key = f"channel:{secret_str}:FutureEvent"
        ttl = self.redis_store.redis_client.ttl(key)
        # TTL should be positive and approximately 6 hours (2 hours until event + 4 hours expiration)
        self.assertGreater(ttl, 0)
        self.assertLess(ttl, 6 * 3600 + 100)  # Allow some margin

    def test_event_expiration_past_event(self):
        """Test that past events are not stored."""
        import pytz
        from datetime import datetime, timedelta
        
        secret_str = generate_secret_str()
        
        # Create an event with a past datetime (more than 4 hours ago)
        past_dt = datetime.now(pytz.utc) - timedelta(hours=5)
        event_data = {
            "group_title": "Sports",
            "tvg_id": "PastEvent",
            "tvg_name": "Past Game",
            "tvg_logo": "sports.png",
            "url_tvg": "",
            "stream_url": "http://sports.com/live",
            "is_event": True,
            "event_datetime_full": past_dt.strftime("%Y-%m-%d %H:%M:%S")
        }
        
        self.redis_store.store_channels(secret_str, [event_data])
        
        # Verify event was NOT stored (expired before storage)
        retrieved_channel_json = self.redis_store.get_channel(secret_str, "PastEvent")
        self.assertIsNone(retrieved_channel_json)

    def test_event_invalid_datetime(self):
        """Test that events with invalid datetime are not stored."""
        secret_str = generate_secret_str()
        
        event_data = {
            "group_title": "Sports",
            "tvg_id": "InvalidEvent",
            "tvg_name": "Invalid Game",
            "tvg_logo": "sports.png",
            "url_tvg": "",
            "stream_url": "http://sports.com/live",
            "is_event": True,
            "event_datetime_full": "invalid-date-format"
        }
        
        self.redis_store.store_channels(secret_str, [event_data])
        
        # Verify event was NOT stored (invalid datetime)
        retrieved_channel_json = self.redis_store.get_channel(secret_str, "InvalidEvent")
        self.assertIsNone(retrieved_channel_json)

if __name__ == '__main__':
    unittest.main()
