import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import unittest
from src.utils import validate_cron_expression, validate_url

class TestUtils(unittest.TestCase):

    def test_validate_cron_expression_valid(self):
        """Test valid cron expressions."""
        # Test standard cron expressions
        self.assertEqual(validate_cron_expression("0 */6 * * *"), "0 */6 * * *")
        self.assertEqual(validate_cron_expression("0 0 * * *"), "0 0 * * *")
        self.assertEqual(validate_cron_expression("*/15 * * * *"), "*/15 * * * *")
        self.assertEqual(validate_cron_expression("0 0 1 * *"), "0 0 1 * *")
        
        # Test with whitespace
        self.assertEqual(validate_cron_expression("  0 */6 * * *  "), "0 */6 * * *")

    def test_validate_cron_expression_invalid(self):
        """Test invalid cron expressions."""
        # Too few fields
        with self.assertRaises(ValueError) as context:
            validate_cron_expression("0 0")
        self.assertIn("Expected 5 fields", str(context.exception))
        
        # Too many fields
        with self.assertRaises(ValueError) as context:
            validate_cron_expression("0 0 * * * *")
        self.assertIn("Expected 5 fields", str(context.exception))
        
        # Empty string
        with self.assertRaises(ValueError) as context:
            validate_cron_expression("")
        self.assertIn("cannot be empty", str(context.exception))
        
        # Invalid field value
        with self.assertRaises(ValueError) as context:
            validate_cron_expression("60 0 * * *")  # Minute > 59
        self.assertIn("Invalid cron expression", str(context.exception))

    def test_validate_url_valid(self):
        """Test valid URLs."""
        # HTTP URLs
        self.assertEqual(validate_url("http://example.com/playlist.m3u"), "http://example.com/playlist.m3u")
        self.assertEqual(validate_url("https://example.com/playlist.m3u"), "https://example.com/playlist.m3u")
        
        # File URLs
        self.assertEqual(validate_url("file:///path/to/playlist.m3u"), "file:///path/to/playlist.m3u")
        
        # URLs with whitespace
        self.assertEqual(validate_url("  http://example.com/playlist.m3u  "), "http://example.com/playlist.m3u")

    def test_validate_url_invalid(self):
        """Test invalid URLs."""
        # Empty string
        with self.assertRaises(ValueError) as context:
            validate_url("")
        self.assertIn("cannot be empty", str(context.exception))
        
        # Missing scheme
        with self.assertRaises(ValueError) as context:
            validate_url("example.com/playlist.m3u")
        self.assertIn("missing scheme", str(context.exception))
        
        # Unsupported scheme
        with self.assertRaises(ValueError) as context:
            validate_url("ftp://example.com/playlist.m3u")
        self.assertIn("unsupported scheme", str(context.exception))
        
        # HTTP without domain
        with self.assertRaises(ValueError) as context:
            validate_url("http://")
        self.assertIn("missing domain", str(context.exception))
        
        # File without path
        with self.assertRaises(ValueError) as context:
            validate_url("file://")
        self.assertIn("missing file path", str(context.exception))

if __name__ == '__main__':
    unittest.main()
