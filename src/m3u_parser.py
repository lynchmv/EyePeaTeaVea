import re
import requests
import os

class M3UParser:
    def __init__(self, m3u_source: str):
        self.m3u_source = m3u_source

    def _get_m3u_content(self) -> str:
        """Fetches the content of an M3U playlist from a URL or reads from a local file."""
        if os.path.exists(self.m3u_source):
            with open(self.m3u_source, 'r') as f:
                return f.read()
        else:
            try:
                response = requests.get(self.m3u_source, timeout=10)
                response.raise_for_status()  # Raise an HTTPError for bad responses (4xx or 5xx)
                return response.text
            except requests.exceptions.RequestException as e:
                print(f"Error fetching M3U from {self.m3u_source}: {e}")
                return ""

    def parse(self) -> list[dict]:
        """Parses M3U content and extracts channel information."""
        content = self._get_m3u_content()
        if not content:
            return []

        channels = []
        lines = content.splitlines()
        channel_info = {}

        for line in lines:
            line = line.strip()
            if line.startswith("#EXTINF"):
                # Extract attributes from #EXTINF line
                group_title_match = re.search(r'group-title="([^"]*)"', line)
                tvg_id_match = re.search(r'tvg-id="([^"]*)"', line)
                tvg_name_match = re.search(r'tvg-name="([^"]*)"', line)
                tvg_logo_match = re.search(r'tvg-logo="([^"]*)"', line)
                url_tvg_match = re.search(r'url-tvg="([^"]*)"', line)

                channel_info = {
                    "group_title": group_title_match.group(1) if group_title_match else "Other",
                    "tvg_id": tvg_id_match.group(1) if tvg_id_match else "",
                    "tvg_name": tvg_name_match.group(1) if tvg_name_match else "",
                    "tvg_logo": tvg_logo_match.group(1) if tvg_logo_match else "",
                    "url_tvg": url_tvg_match.group(1) if url_tvg_match else "",
                    "stream_url": ""
                }
            elif line and not line.startswith("#") and channel_info:
                # The next non-comment line after #EXTINF is the stream URL
                channel_info["stream_url"] = line
                channels.append(channel_info)
                channel_info = {}  # Reset for the next channel
        return channels

if __name__ == "__main__":
    # Example Usage (for testing purposes)
    # You would typically get this URL from your .env file
    example_m3u_path = "/home/lynchmv/development/EyePeaTeaVea/example.m3u" # Using local file for testing
    parser = M3UParser(example_m3u_path)
    parsed_channels = parser.parse()
    for channel in parsed_channels:
        print(channel)
