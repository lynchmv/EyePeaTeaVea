import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
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

    def test_parse_m3u_with_leading_comment(self):
        commented_m3u_content = """# This is a comment
#EXTM3U
#EXTINF:-1 tvg-id="Test1" tvg-name="Test Channel 1" group-title="Test",Test Channel 1
http://test1.com/live
"""
        commented_m3u_file = "test_commented.m3u"
        with open(commented_m3u_file, "w") as f:
            f.write(commented_m3u_content)

        parser = M3UParser(commented_m3u_file)
        channels = parser.parse()

        self.assertEqual(len(channels), 1)
        self.assertEqual(channels[0]["tvg_id"], "Test1")
        self.assertEqual(channels[0]["tvg_name"], "Test Channel 1")
        self.assertEqual(channels[0]["group_title"], "Test")
        self.assertEqual(channels[0]["stream_url"], "http://test1.com/live")

        os.remove(commented_m3u_file)

    def test_parse_m3u_with_extgrp(self):
        extgrp_m3u_content = """
#EXTM3U
#EXTGRP:TheTVApp - NBA
#EXTINF:-1 tvg-id="NBA.Basketball.Dummy.us" tvg-name="Los Angeles Clippers @ Phoenix Suns - 11/7/25, 2:00:00 AM UTC HD" tvg-logo="http://drewlive24.duckdns.org:9000/Logos/NBA.png" ,Los Angeles Clippers @ Phoenix Suns - 11/7/25 - 2:00:00 AM UTC HD
https://v8.thetvapp.to/hls/NBATV/tracks-v1a1/mono.m3u8?token=s-zMv_W_mbBLorBvEK0BFA&expires=1762473154&user_id=Z1BLOXE3M1JGcHZ3a0Iwam5ReWNOcUp0dGdJV1NjT3JYRHpMYThJUg==
#EXTINF:-1 tvg-id="NBA.Basketball.Dummy.us" tvg-name="Los Angeles Clippers @ Phoenix Suns - 11/7/25, 2:00:00 AM UTC SD" tvg-logo="http://drewlive24.duckdns.org:9000/Logos/NBA.png" ,Los Angeles Clippers @ Phoenix Suns - 11/7/25 - 2:00:00 AM UTC SD
#EXTGRP:TheTVApp - NCAAF
#EXTINF:-1 tvg-id="NCAA.Football.Dummy.us" tvg-name="Georgia Southern Eagles @ Appalachian State Mountaineers - 11/7/25, 12:30:00 AM UTC HD" tvg-logo="http://drewlive24.duckdns.org:9000/Logos/CFB.png" ,Georgia Southern Eagles @ Appalachian State Mountaineers - 11/7/25 - 12:30:00 AM UTC HD
https://v2.thetvapp.to/hls/ESPN2/tracks-v1a1/mono.m3u8?token=aoVFMEujepl6xpDrcKxawA&expires=1762473178&user_id=Z1BLOXE3M1JGcHZ3a0Iwam5ReWNOcUp0dGdJV1NjT3JYRHpMYThJUg==
#EXTINF:-1 tvg-id="NCAA.Football.Dummy.us" tvg-name="Georgia Southern Eagles @ Appalachian State Mountaineers - 11/7/25, 12:30:00 AM UTC SD" tvg-logo="http://drewlive24.duckdns.org:9000/Logos/CFB.png" ,Georgia Southern Eagles @ Appalachian State Mountaineers - 11/7/25 - 12:30:00 AM UTC SD
#EXTGRP:TheTVApp - NFL
#EXTINF:-1 tvg-id="NFL.Dummy.us" tvg-name="Las Vegas Raiders @ Denver Broncos - 11/7/25, 1:15:00 AM UTC HD" tvg-logo="http://drewlive24.duckdns.org:9000/Logos/NFL.png" ,Las Vegas Raiders @ Denver Broncos - 11/7/25 - 1:15:00 AM UTC HD
https://v12.thetvapp.to/hls/tsn1/tracks-v1a1/mono.m3u8?token=_1VjHmli_L9tSAdPHNVTbw&expires=1762473166&user_id=Z1BLOXE3M1JGcHZ3a0Iwam5ReWNOcUp0dGdJV1NjT3JYRHpMYThJUg==
#EXTINF:-1 tvg-id="NFL.Dummy.us" tvg-name="Las Vegas Raiders @ Denver Broncos - 11/7/25, 1:15:00 AM UTC SD" tvg-logo="http://drewlive24.duckdns.org:9000/Logos/NFL.png" ,Las Vegas Raiders @ Denver Broncos - 11/7/25 - 1:15:00 AM UTC SD
"""
        extgrp_m3u_file = "test_extgrp.m3u"
        with open(extgrp_m3u_file, "w") as f:
            f.write(extgrp_m3u_content)

        parser = M3UParser(extgrp_m3u_file)
        channels = parser.parse()

        self.assertEqual(len(channels), 3) # Only 3 events (HD versions) are expected to be parsed

        # Verify NBA channel
        self.assertEqual(channels[0]["group_title"], "TheTVApp - NBA")

        # Verify NCAAF channel
        self.assertEqual(channels[1]["group_title"], "TheTVApp - NCAAF")

        # Verify NFL channel
        self.assertEqual(channels[2]["group_title"], "TheTVApp - NFL")

        os.remove(extgrp_m3u_file)

    def test_event_title_format(self):
        event_m3u_content = """
#EXTM3U
#EXTINF:-1 tvg-id="Event1" tvg-name="11/08/25 08:10:00 PM EST = Portland Trail Blazers @ Miami Heat" group-title="Sports",Event 1
http://event1.com/live
"""
        event_m3u_file = "test_event.m3u"
        with open(event_m3u_file, "w") as f:
            f.write(event_m3u_content)

        parser = M3UParser(event_m3u_file)
        channels = parser.parse()
        
        self.assertEqual(len(channels), 1)
        self.assertEqual(channels[0]["event_title"], "Portland Trail Blazers @ Miami Heat\nNov 8 8:10PM")

        os.remove(event_m3u_file)

if __name__ == '__main__':
    unittest.main()
