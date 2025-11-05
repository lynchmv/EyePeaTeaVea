import xml.etree.ElementTree as ET
import requests
from datetime import datetime
import io
import os
import gzip

class EPGParser:
    def __init__(self, epg_source: str):
        self.epg_source = epg_source

    def _get_epg_content(self) -> str:
        """Fetches the content of an EPG XMLTV file from a URL or reads from a local file."""
        if os.path.exists(self.epg_source):
            with open(self.epg_source, 'rb') as f:
                return f.read().decode('utf-8')
        else:
            try:
                response = requests.get(self.epg_source, timeout=30)
                response.raise_for_status()
                
                if self.epg_source.endswith('.gz') or response.headers.get('Content-Encoding') == 'gzip':
                    return gzip.decompress(response.content).decode('utf-8')
                else:
                    return response.text
            except requests.exceptions.RequestException as e:
                print(f"Error fetching EPG from {self.epg_source}: {e}")
                return ""

    def parse(self) -> tuple[list[dict], list[dict]]:
        """Parses EPG XMLTV content and extracts channel and program information."""
        content = self._get_epg_content()
        if not content:
            return [], []

        channels = {}
        programs = []

        # Use iterparse for efficient parsing of large XML files
        # Wrap the string content in a StringIO object for iterparse
        content_file = io.StringIO(content)
        for event, elem in ET.iterparse(content_file, events=('start', 'end')):
            if event == 'end':
                if elem.tag == 'channel':
                    channel_id = elem.get('id')
                    display_name = elem.find('display-name').text if elem.find('display-name') is not None else ""
                    channels[channel_id] = {
                        "id": channel_id,
                        "display_name": display_name,
                        "icon": elem.find('icon').get('src') if elem.find('icon') is not None else ""
                    }
                    elem.clear() # Clear element from memory
                elif elem.tag == 'programme':
                    program_info = {
                        "start": elem.get('start'),
                        "stop": elem.get('stop'),
                        "channel": elem.get('channel'),
                        "title": elem.find('title').text if elem.find('title') is not None else "",
                        "desc": elem.find('desc').text if elem.find('desc') is not None else "",
                        "category": elem.find('category').text if elem.find('category') is not None else "",
                        "icon": elem.find('icon').get('src') if elem.find('icon') is not None else "",
                        "episode_num": elem.find('episode-num').text if elem.find('episode-num') is not None else "",
                        "rating": elem.find('rating').find('value').text if elem.find('rating') is not None and elem.find('rating').find('value') is not None else ""
                    }
                    programs.append(program_info)
                    elem.clear() # Clear element from memory
        return list(channels.values()), programs

if __name__ == "__main__":
    # Example Usage (for testing purposes)
    # Using local file for testing
    example_epg_path = "/home/lynchmv/development/EyePeaTeaVea/example.xml"
    parser = EPGParser(example_epg_path)
    parsed_channels, parsed_programs = parser.parse()
    print(f"Parsed {len(parsed_channels)} channels and {len(parsed_programs)} programs.")
    # Print a few samples to verify
    print("\nSample Channels:")
    for i, channel_info in enumerate(parsed_channels):
        if i >= 5: break
        print(channel_info)
    
    print("\nSample Programs:")
    for i, program_info in enumerate(parsed_programs):
        if i >= 5: break
        print(program_info)
