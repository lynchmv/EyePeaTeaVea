import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import unittest
from unittest.mock import Mock, patch, MagicMock
from src.scheduler import Scheduler
from src.models import UserData
from src.utils import generate_secret_str

class TestScheduler(unittest.TestCase):

    def setUp(self):
        # Mock RedisStore to avoid needing actual Redis connection
        self.mock_redis_store = Mock()
        with patch('src.scheduler.RedisStore', return_value=self.mock_redis_store):
            self.scheduler = Scheduler()
            self.scheduler.redis_store = self.mock_redis_store

    def test_parse_cron_expression_valid(self):
        """Test parsing valid cron expressions."""
        cron_trigger = self.scheduler._parse_cron_expression("0 */6 * * *")
        self.assertIsNotNone(cron_trigger)
        
        cron_trigger = self.scheduler._parse_cron_expression("0 0 * * *")
        self.assertIsNotNone(cron_trigger)

    def test_parse_cron_expression_invalid(self):
        """Test parsing invalid cron expressions."""
        with self.assertRaises(ValueError):
            self.scheduler._parse_cron_expression("0 0")
        
        with self.assertRaises(ValueError):
            self.scheduler._parse_cron_expression("invalid")

    def test_trigger_m3u_fetch_for_user(self):
        """Test triggering M3U fetch for a user."""
        secret_str = generate_secret_str()
        user_data = UserData(
            m3u_sources=["http://example.com/playlist.m3u"],
            parser_schedule_crontab="0 */6 * * *",
            host_url="http://localhost:8020"
        )
        
        # Mock M3UParser
        mock_parser = Mock()
        mock_parser.parse.return_value = [
            {"tvg_id": "CNN", "tvg_name": "CNN", "group_title": "News", "tvg_logo": "", "url_tvg": "", "stream_url": "http://cnn.com", "is_event": False}
        ]
        
        with patch('src.scheduler.M3UParser', return_value=mock_parser):
            self.scheduler.trigger_m3u_fetch_for_user(secret_str, user_data)
        
        # Verify store_channels was called
        self.mock_redis_store.store_channels.assert_called_once()
        call_args = self.mock_redis_store.store_channels.call_args
        self.assertEqual(call_args[0][0], secret_str)
        self.assertEqual(len(call_args[0][1]), 1)

    def test_scheduled_fetch_wrapper(self):
        """Test scheduled fetch wrapper retrieves user data."""
        secret_str = generate_secret_str()
        user_data = UserData(
            m3u_sources=["http://example.com/playlist.m3u"],
            parser_schedule_crontab="0 */6 * * *",
            host_url="http://localhost:8020"
        )
        
        self.mock_redis_store.get_user_data.return_value = user_data
        
        # Mock M3UParser
        mock_parser = Mock()
        mock_parser.parse.return_value = []
        
        with patch('src.scheduler.M3UParser', return_value=mock_parser):
            self.scheduler._scheduled_fetch_wrapper(secret_str)
        
        self.mock_redis_store.get_user_data.assert_called_once_with(secret_str)

    def test_scheduled_fetch_wrapper_no_user_data(self):
        """Test scheduled fetch wrapper when user data not found."""
        secret_str = generate_secret_str()
        self.mock_redis_store.get_user_data.return_value = None
        
        self.scheduler._scheduled_fetch_wrapper(secret_str)
        
        # Should not call store_channels if user data not found
        self.mock_redis_store.store_channels.assert_not_called()

    def test_start_scheduler_no_users(self):
        """Test starting scheduler with no users."""
        self.mock_redis_store.get_all_secret_strs.return_value = []
        self.scheduler.scheduler = Mock()
        self.scheduler.scheduler.running = False
        
        self.scheduler.start_scheduler()
        
        # Should not add any jobs
        self.scheduler.scheduler.add_job.assert_not_called()

    def test_start_scheduler_with_users(self):
        """Test starting scheduler with users."""
        secret_str = generate_secret_str()
        user_data = UserData(
            m3u_sources=["http://example.com/playlist.m3u"],
            parser_schedule_crontab="0 */6 * * *",
            host_url="http://localhost:8020"
        )
        
        self.mock_redis_store.get_all_secret_strs.return_value = [secret_str]
        self.mock_redis_store.get_user_data.return_value = user_data
        
        self.scheduler.scheduler = Mock()
        self.scheduler.scheduler.running = False
        
        self.scheduler.start_scheduler()
        
        # Should add a job for the user
        self.scheduler.scheduler.add_job.assert_called_once()
        call_args = self.scheduler.scheduler.add_job.call_args
        self.assertEqual(call_args[1]["id"], f"m3u_fetch_{secret_str}")

if __name__ == '__main__':
    unittest.main()
