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
        channel_data = {
            "group_title": "News",
            "tvg_id": "CNN",
            "tvg_name": "CNN",
            "tvg_logo": "cnn.png",
            "url_tvg": "",
            "stream_url": "http://cnn.com/live"
        }
        self.redis_store.store_channels({channel_data["tvg_id"]: channel_data})
        retrieved_channel_json = self.redis_store.get_channel("CNN")
        self.assertIsNotNone(retrieved_channel_json)
        retrieved_channel = json.loads(retrieved_channel_json)
        self.assertEqual(retrieved_channel["tvg_id"], "CNN")
        self.assertEqual(retrieved_channel["stream_url"], "http://cnn.com/live")

    def test_get_all_channels(self):
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
        self.redis_store.store_channels({
            channel_data_1["tvg_id"]: channel_data_1,
            channel_data_2["tvg_id"]: channel_data_2
        })
        all_channels = self.redis_store.get_all_channels()
        self.assertEqual(len(all_channels), 2)
        self.assertIn("CNN", all_channels)
        self.assertIn("ESPN", all_channels)


    def test_clear_all_data(self):
        channel_data = {
            "group_title": "News",
            "tvg_id": "CNN",
            "tvg_name": "CNN",
            "tvg_logo": "cnn.png",
            "url_tvg": "",
            "stream_url": "http://cnn.com/live"
        }
        self.redis_store.store_channels({channel_data["tvg_id"]: channel_data})
        self.redis_store.clear_all_data()
        all_channels = self.redis_store.get_all_channels()
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

if __name__ == '__main__':
    unittest.main()
