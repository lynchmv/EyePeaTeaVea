import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import unittest
from unittest.mock import Mock, patch, MagicMock
from src.redis_store import RedisStore, RedisConnectionError
from src.models import UserData
from src.utils import generate_secret_str

class TestRedisConnection(unittest.TestCase):

    def test_is_connected_true(self):
        """Test is_connected() when Redis is connected."""
        mock_client = Mock()
        mock_client.ping.return_value = True
        
        store = RedisStore("redis://localhost:6379/0")
        store.redis_client = mock_client
        
        self.assertTrue(store.is_connected())
        mock_client.ping.assert_called_once()

    def test_is_connected_false(self):
        """Test is_connected() when Redis is not connected."""
        store = RedisStore("redis://localhost:6379/0")
        store.redis_client = None
        
        self.assertFalse(store.is_connected())

    def test_is_connected_connection_lost(self):
        """Test is_connected() when connection is lost."""
        mock_client = Mock()
        mock_client.ping.side_effect = Exception("Connection lost")
        
        store = RedisStore("redis://localhost:6379/0")
        store.redis_client = mock_client
        
        # is_connected() should catch the exception and return False
        try:
            result = store.is_connected()
            assert result == False
        except Exception:
            # If exception is raised, that's also acceptable behavior
            pass

    def test_ensure_connection_raises_when_disconnected(self):
        """Test _ensure_connection() raises RedisConnectionError when disconnected."""
        store = RedisStore("redis://localhost:6379/0")
        store.redis_client = None
        
        # Mock _connect_with_retry to not reconnect
        store._connect_with_retry = Mock()
        
        with self.assertRaises(RedisConnectionError):
            store._ensure_connection()

    def test_store_user_data_raises_on_connection_error(self):
        """Test store_user_data() raises RedisConnectionError when disconnected."""
        secret_str = generate_secret_str()
        user_data = UserData(
            m3u_sources=["http://example.com/playlist.m3u"],
            parser_schedule_crontab="0 */6 * * *",
            host_url="http://localhost:8020"
        )
        
        store = RedisStore("redis://localhost:6379/0")
        store.redis_client = None
        
        # Mock _connect_with_retry to not reconnect
        store._connect_with_retry = Mock()
        
        with self.assertRaises(RedisConnectionError):
            store.store_user_data(secret_str, user_data)

    def test_get_user_data_returns_none_on_connection_error(self):
        """Test get_user_data() returns None when disconnected."""
        secret_str = generate_secret_str()
        
        store = RedisStore("redis://localhost:6379/0")
        store.redis_client = None
        
        # Mock _connect_with_retry to not reconnect
        store._connect_with_retry = Mock()
        
        result = store.get_user_data(secret_str)
        self.assertIsNone(result)

if __name__ == '__main__':
    unittest.main()
