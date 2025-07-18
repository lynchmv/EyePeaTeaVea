import logging
import httpx
import collections
import re
from ipytv import playlist
from ipytv.channel import IPTVAttr
from urllib.parse import urlparse
import os
from datetime import datetime
from dateparser.search import search_dates
import asyncio

from stremio_addon.db import models, crud
from stremio_addon.utils import validation_helper, crypto
from stremio_addon.db.redis_database import REDIS_ASYNC_CLIENT

class CombinedPlaylistParser:
    """
    Fetches multiple source playlists, combines them, and parses the result,
    now with cooperative multitasking to reduce CPU load.
    """
    def __init__(self, source_urls: list[str]):
        self.source_urls = source_urls
        self.playlist_source = "Combined Playlist"
        logging.info(f"Parser initialized for {len(source_urls)} source URLs.")

    async def _generate_combined_content(self) -> str | None:
        final_m3u_string = "#EXTM3U\n"
        async with httpx.AsyncClient() as client:
            for url in self.source_urls:
                try:
                    response = await client.get(url, follow_redirects=True, timeout=30)
                    response.raise_for_status()
                    path = urlparse(url).path
                    default_group_name = os.path.basename(path)
                    for line in response.text.splitlines():
                        if line.startswith("#EXTINF"):
                            if 'group-title' not in line:
                                line = line.replace('EXTINF:-1', f'EXTINF:-1 group-title="{default_group_name}"')
                            final_m3u_string += line + "\n"
                        elif line.startswith("http"):
                            final_m3u_string += line + "\n"
                except httpx.RequestError as e:
                    logging.error(f"Failed to fetch source playlist {url}: {e}")
                    continue
        return final_m3u_string

    async def parse(self) -> dict:
        content = await self._generate_combined_content()
        if not content:
            return {"channels": [], "events": []}

        iptv_playlist = playlist.loads(content)
        channels = list(iptv_playlist)

        parsed_data = {"channels": [], "events": []}
        logging.info(f"Found {len(channels)} total entries to process.")

        date_pattern = re.compile(r'\d{1,2}/\d{1,2}/\d{2,4}|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b \d{1,2}, \d{4}')
        time_pattern = re.compile(r'\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM|ET|EST|EDT|UTC)', re.IGNORECASE)

        processed_count = 0
        for channel in channels:
            # Yield control to the event loop every 100 items to prevent high CPU usage
            if processed_count > 0 and processed_count % 100 == 0:
                await asyncio.sleep(0)
            processed_count += 1

            if not channel.url:
                continue

            raw_name = channel.name.strip()
            is_event = date_pattern.search(raw_name) and time_pattern.search(raw_name)

            if is_event:
                try:
                    found_dates = search_dates(raw_name)
                    if not found_dates:
                        raise ValueError("Date could not be found in title")

                    event_datetime = found_dates[0][1]
                    event_start_timestamp = int(event_datetime.timestamp())

                    unique_str = f"{raw_name}{event_start_timestamp}"
                    event_id = f"event_{crypto.get_text_hash(unique_str)}"
                    poster_url = channel.attributes.get(IPTVAttr.TVG_LOGO.value)
                    group_title = channel.attributes.get('group-title', 'Live Events')

                    event_metadata = models.MediaFusionEventsMetaData(
                        id=event_id,
                        title=raw_name,
                        event_start_timestamp=event_start_timestamp,
                        poster=poster_url if validation_helper.is_valid_url(poster_url) else None,
                        genres=[group_title],
                        streams=[models.TVStreams(meta_id=event_id, name=raw_name, url=channel.url, source=self.playlist_source)]
                    )
                    parsed_data["events"].append(event_metadata)
                except Exception as e:
                    logging.warning(f"Skipping event due to processing error: '{raw_name}' | Error: {e}")
            else:
                clean_name = channel.attributes.get(IPTVAttr.TVG_NAME.value, raw_name)
                channel_name = re.sub(r"\s+", " ", clean_name).strip()

                if len(channel_name) < 2:
                    continue

                channel_id = f"tv_{crypto.get_text_hash(channel_name)}"
                poster_url = channel.attributes.get(IPTVAttr.TVG_LOGO.value)

                channel_metadata = models.MediaFusionTVMetaData(
                    id=channel_id,
                    title=channel_name,
                    poster=poster_url if validation_helper.is_valid_url(poster_url) else None,
                    logo=poster_url if validation_helper.is_valid_url(poster_url) else None,
                    streams=[models.TVStreams(meta_id=channel_id, name=channel_name, url=channel.url, source=self.playlist_source)]
                )
                parsed_data["channels"].append(channel_metadata)

        logging.info(f"Parsing complete. Found {len(parsed_data['channels'])} channels and {len(parsed_data['events'])} events.")
        return parsed_data

