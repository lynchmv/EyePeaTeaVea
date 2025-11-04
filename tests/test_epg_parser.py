import unittest
import os
from src.epg_parser import EPGParser

class TestEPGParser(unittest.TestCase):

    def setUp(self):
        self.test_epg_content = """<?xml version=\"1.0\" encoding=\"utf-8\"?>
<tv generator-info-name=\"TestGenerator\">
  <channel id=\"CNN\">
    <display-name>CNN</display-name>
    <icon src=\"http://example.com/cnn.png\"/>
  </channel>
  <channel id=\"ESPN\">
    <display-name>ESPN</display-name>
    <icon src=\"http://example.com/espn.png\"/>
  </channel>
  <programme start=\"20251104100000 +0000\" stop=\"20251104110000 +0000\" channel=\"CNN\">
    <title>CNN News</title>
    <desc>Daily news update</desc>
    <category>News</category>
  </programme>
  <programme start=\"20251104110000 +0000\" stop=\"20251104120000 +0000\" channel=\"CNN\">
    <title>CNN Special</title>
    <desc>Special report</desc>
    <category>News</category>
  </programme>
  <programme start=\"20251104100000 +0000\" stop=\"20251104110000 +0000\" channel=\"ESPN\">
    <title>SportsCenter</title>
    <desc>Latest sports news</desc>
    <category>Sports</category>
  </programme>
</tv>
"""
        self.test_epg_file = "test.xml"
        with open(self.test_epg_file, "w") as f:
            f.write(self.test_epg_content)

    def tearDown(self):
        if os.path.exists(self.test_epg_file):
            os.remove(self.test_epg_file)

    def test_parse_epg(self):
        parser = EPGParser(self.test_epg_file)
        channels, programs = parser.parse()

        self.assertEqual(len(channels), 2)
        self.assertEqual(channels[0]["id"], "CNN")
        self.assertEqual(channels[1]["id"], "ESPN")

        self.assertEqual(len(programs), 3)

        cnn_programs = [p for p in programs if p["channel"] == "CNN"]
        espn_programs = [p for p in programs if p["channel"] == "ESPN"]

        self.assertEqual(len(cnn_programs), 2)
        self.assertEqual(cnn_programs[0]["title"], "CNN News")
        self.assertEqual(cnn_programs[1]["title"], "CNN Special")

        self.assertEqual(len(espn_programs), 1)
        self.assertEqual(espn_programs[0]["title"], "SportsCenter")

if __name__ == '__main__':
    unittest.main()
