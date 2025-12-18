import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import unittest
import json
from src.catalog_utils import filter_channels, create_meta

class TestCatalogUtils(unittest.TestCase):

    def setUp(self):
        self.sample_channels = {
            "CNN": json.dumps({
                "group_title": "News",
                "tvg_id": "CNN",
                "tvg_name": "CNN",
                "tvg_logo": "cnn.png",
                "url_tvg": "",
                "stream_url": "http://cnn.com/live",
                "is_event": False
            }),
            "ESPN": json.dumps({
                "group_title": "Sports",
                "tvg_id": "ESPN",
                "tvg_name": "ESPN",
                "tvg_logo": "espn.png",
                "url_tvg": "",
                "stream_url": "http://espn.com/live",
                "is_event": False
            }),
            "NBA_Event": json.dumps({
                "group_title": "NBA",
                "tvg_id": "NBA_Event",
                "tvg_name": "Lakers vs Celtics",
                "tvg_logo": "nba.png",
                "url_tvg": "",
                "stream_url": "http://nba.com/live",
                "is_event": True,
                "event_title": "Lakers vs Celtics\nNov 8 8:00PM",
                "event_sport": "Basketball"
            })
        }

    def test_filter_channels_tv_type(self):
        """Test filtering channels by type 'tv'."""
        filtered = filter_channels(self.sample_channels, "tv")
        self.assertEqual(len(filtered), 2)
        self.assertEqual(filtered[0]["tvg_id"], "CNN")
        self.assertEqual(filtered[1]["tvg_id"], "ESPN")
        # Events should be excluded
        self.assertNotIn("NBA_Event", [ch["tvg_id"] for ch in filtered])

    def test_filter_channels_events_type(self):
        """Test filtering channels by type 'events'."""
        filtered = filter_channels(self.sample_channels, "events")
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["tvg_id"], "NBA_Event")
        # Regular channels should be excluded
        self.assertNotIn("CNN", [ch["tvg_id"] for ch in filtered])
        self.assertNotIn("ESPN", [ch["tvg_id"] for ch in filtered])

    def test_filter_channels_by_genre(self):
        """Test filtering channels by genre."""
        filtered = filter_channels(self.sample_channels, "tv", "genre", "News")
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["group_title"], "News")
        self.assertEqual(filtered[0]["tvg_id"], "CNN")

    def test_filter_channels_by_search(self):
        """Test filtering channels by search term."""
        filtered = filter_channels(self.sample_channels, "tv", "search", "CNN")
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["tvg_id"], "CNN")
        
        # Case insensitive search
        filtered = filter_channels(self.sample_channels, "tv", "search", "cnn")
        self.assertEqual(len(filtered), 1)
        
        # No results
        filtered = filter_channels(self.sample_channels, "tv", "search", "nonexistent")
        self.assertEqual(len(filtered), 0)

    def test_filter_channels_empty(self):
        """Test filtering with empty channel data."""
        filtered = filter_channels({}, "tv")
        self.assertEqual(len(filtered), 0)

    def test_filter_channels_sorted(self):
        """Test that filtered channels are sorted."""
        filtered = filter_channels(self.sample_channels, "tv")
        # Should be sorted by tvg_name
        self.assertEqual(filtered[0]["tvg_name"], "CNN")
        self.assertEqual(filtered[1]["tvg_name"], "ESPN")

    def test_create_meta_tv_channel(self):
        """Test creating meta for a TV channel."""
        channel = json.loads(self.sample_channels["CNN"])
        meta = create_meta(channel, "test_secret", "test_prefix", "http://test.com")
        
        self.assertEqual(meta["type"], "tv")
        self.assertEqual(meta["name"], "CNN")
        self.assertEqual(meta["id"], "test_prefixCNN")
        self.assertIn("poster", meta)
        self.assertIn("background", meta)
        self.assertIn("logo", meta)
        self.assertEqual(meta["genres"], ["News"])

    def test_create_meta_event(self):
        """Test creating meta for an event."""
        channel = json.loads(self.sample_channels["NBA_Event"])
        meta = create_meta(channel, "test_secret", "test_prefix", "http://test.com")
        
        self.assertEqual(meta["type"], "events")
        self.assertEqual(meta["name"], "Lakers vs Celtics\nNov 8 8:00PM")
        self.assertIn("test_prefix_event_", meta["id"])
        self.assertEqual(meta["genres"], ["Basketball"])

if __name__ == '__main__':
    unittest.main()
