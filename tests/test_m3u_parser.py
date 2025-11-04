import unittest
import os
from src.m3u_parser import M3UParser

class TestM3UParser(unittest.TestCase):

    def setUp(self):
        self.test_m3u_content = """
#EXTM3U
#EXTINF:-1 tvg-id="CNN" tvg-name="CNN" tvg-logo="cnn.png" group-title="News",CNN
http://cnn.com/live
#EXTINF:-1 tvg-id="ESPN" tvg-name="ESPN" tvg-logo="espn.png" group-title="Sports",ESPN
http://espn.com/live
"""
        self.test_m3u_file = "test.m3u"
        with open(self.test_m3u_file, "w") as f:
            f.write(self.test_m3u_content)

    def tearDown(self):
        if os.path.exists(self.test_m3u_file):
            os.remove(self.test_m3u_file)

    def test_parse_m3u(self):
        parser = M3UParser(self.test_m3u_file)
        channels = parser.parse()

        self.assertEqual(len(channels), 2)

        self.assertEqual(channels[0]["tvg_id"], "CNN")
        self.assertEqual(channels[0]["tvg_name"], "CNN")
        self.assertEqual(channels[0]["tvg_logo"], "cnn.png")
        self.assertEqual(channels[0]["group_title"], "News")
        self.assertEqual(channels[0]["stream_url"], "http://cnn.com/live")

        self.assertEqual(channels[1]["tvg_id"], "ESPN")
        self.assertEqual(channels[1]["tvg_name"], "ESPN")
        self.assertEqual(channels[1]["tvg_logo"], "espn.png")
        self.assertEqual(channels[1]["group_title"], "Sports")
        self.assertEqual(channels[1]["stream_url"], "http://espn.com/live")

if __name__ == '__main__':
    unittest.main()
