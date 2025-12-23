"""
M3U playlist parser for extracting channel and event information.

This module provides functionality to parse M3U playlists and extract:
- Channel metadata (name, logo, group, etc.)
- Event information (sports events with dates/times)
- Stream URLs

Handles various M3U formats and timezone conversions.
"""
import re
import requests
import os
import hashlib
import logging
from ipytv import playlist
from ipytv.channel import IPTVAttr
from urllib.parse import urljoin
from dotenv import load_dotenv
from datetime import datetime
import pytz

load_dotenv()

logger = logging.getLogger(__name__)

HOST_URL = os.getenv("HOST_URL", "http://localhost:8020")

class M3UParser:
    """
    Parser for M3U playlist files.
    
    Parses M3U playlists from URLs or local files and extracts channel
    and event information. Handles timezone conversion and event detection.
    
    Attributes:
        m3u_source: URL or file path to the M3U playlist
    """
    def __init__(self, m3u_source: str):
        self.m3u_source = m3u_source

    def extract_event_datetime(self, tvg_name: str) -> datetime | None:
        """
        Extract and parse the most relevant datetime from messy TVG-style event strings.
        Prefers US time zones (EST/EDT > CST/CDT > MST/MDT > PST/PDT > UK/UTC)
        and returns a UTC-aware datetime for consistency.
        
        Args:
            tvg_name: TVG-style event string containing date/time information
            
        Returns:
            UTC-aware datetime object if parsing succeeds, None otherwise
        """
        import re, dateparser, pytz
        from datetime import datetime

        s = tvg_name.strip()

        # 1️⃣ Handle cases like "= ..." or " - ..."
        if "=" in s:
            s = s.split("=")[0].strip()
        elif " - " in s:
            s = s.split(" - ")[-1].strip()

        # 2️⃣ Extract parenthesized multi-timezone portion if present
        match = re.search(r"\(([^)]*?(EST|EDT|CST|CDT|MST|MDT|PST|PDT|UK|UTC)[^)]*?)\)", s)
        if match:
            inner = match.group(1)

            preferred_zones = ["EST", "EDT", "CST", "CDT", "MST", "MDT", "PST", "PDT", "UK", "UTC"]
            tz_match = None

            # Split on "/" and pick first segment containing preferred timezone
            for part in [p.strip() for p in inner.split('/')]:
                for tz in preferred_zones:
                    if tz in part:
                        tz_match = part
                        break
                if tz_match:
                    break

            if tz_match:
                s = tz_match
            else:
                s = inner.split('/')[0].strip()

        # 3️⃣ Normalize formats like "Nov-06-2025" → "Nov 06 2025"
        s_before = s
        s = re.sub(r"([A-Za-z]{3,})-([0-9]{1,2})-([0-9]{4})", r"\1 \2 \3", s)

        # 🆕 Handle cases like "UTC HD" or "UTC SD"
        s_before = s
        s = re.sub(r"UTC\s+(HD|SD)\b", "UTC", s)

        # LYNCH
        if re.search(r"\(\d{1,2}:\d{2}", s):
            s = re.sub(r"\(\d{1,2}:\d{2}", r"\(", s)

        tz_map = {
            "UK": "UTC",
            "UTC": "UTC",
            "EST": "EST",
            "EDT": "EDT",
            "CST": "CST",
            "CDT": "CDT",
            "MST": "MST",
            "MDT": "MDT",
            "PST": "PST",
            "PDT": "PDT"
        }

        for tz_abbr, tz_full in tz_map.items():
            if tz_abbr in s:
                s = s.replace(tz_abbr, tz_full)

        # 🆕 Remove redundant 24-hour times if 12-hour AM/PM exists
        if re.search(r"\d{1,2}:\d{2} [AP]M", s):
            s_before = s
            s = re.sub(r"^\d{1,2}:\d{2}\s+", "", s)

        # 4️⃣ Remove stray characters that confuse parsing
        s_before = s
        s = re.sub(r"[^A-Za-z0-9: \-/]", " ", s)

        # 5️⃣ Parse to datetime
        dt = dateparser.parse(s)

        if not dt:
            return None


        # 6️⃣ Ensure timezone awareness and convert to UTC
        if not dt.tzinfo:
            if any(tz in s for tz in ["EST", "EDT"]):
                dt = pytz.timezone("US/Eastern").localize(dt)
            elif any(tz in s for tz in ["CST", "CDT"]):
                dt = pytz.timezone("US/Central").localize(dt)
            elif any(tz in s for tz in ["MST", "MDT"]):
                dt = pytz.timezone("US/Mountain").localize(dt)
            elif any(tz in s for tz in ["PST", "PDT"]):
                dt = pytz.timezone("US/Pacific").localize(dt)
            elif "UK" in s:
                dt = pytz.timezone("Europe/London").localize(dt)
            else:
                dt = pytz.UTC.localize(dt)

        dt_utc = dt.astimezone(pytz.UTC)
        return dt_utc

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
                logger.error(f"Error fetching M3U from {self.m3u_source}: {e}")
                return ""
    
    def extract_epg_urls(self) -> list[str]:
        """
        Extract EPG URLs from M3U file.
        
        Looks for url-tvg attribute in #EXTM3U header and per-channel.
        Returns list of unique EPG URLs found.
        """
        content = self._get_m3u_content()
        if not content:
            return []
        
        epg_urls = set()
        lines = content.splitlines()
        
        # Check #EXTM3U header for url-tvg
        for line in lines:
            if line.startswith("#EXTM3U"):
                # Look for url-tvg in the header
                if "url-tvg" in line:
                    import re
                    match = re.search(r'url-tvg="([^"]+)"', line)
                    if match:
                        epg_urls.add(match.group(1))
                break
        
        # Also check per-channel url-tvg (though less common)
        # This is already extracted in parse() method, but we'll collect unique ones here too
        # The parse() method stores url_tvg per channel, so we can extract from parsed channels
        
        return list(epg_urls)

    def _preprocess_m3u_content(self, content: str) -> str:
        """
        Pre-processes M3U content to ensure each #EXTINF line has a group-title attribute.
        If missing, it tries to infer it from #EXTGRP or uses a default.
        """
        lines = content.splitlines()
        processed_lines = []
        current_group = "Uncategorized" # Default group if none found

        for line in lines:
            if line.startswith("#EXTM3U"):
                processed_lines.append(line)
            elif line.startswith("#EXTGRP:"):
                current_group = line.split(":", 1)[1].strip()
            elif line.startswith("#EXTINF:"):
                if "group-title" not in line:
                    # Inject group-title using the current_group
                    line = line.replace("EXTINF:-1", f'EXTINF:-1 group-title="{current_group}"')
                processed_lines.append(line)
            else:
                processed_lines.append(line)
        return "\n".join(processed_lines)

    def parse(self) -> list[dict]:
        """Parses M3U content using ipytv and extracts channel information."""
        raw_content = self._get_m3u_content()
        if not raw_content:
            return []

        # Parse raw content to extract EXTVLCOPT tags BEFORE preprocessing
        # (they're not in ipytv's parsed structure)
        raw_lines = raw_content.splitlines()
        channel_vlcopts = {}  # Map channel index to VLC options
        
        current_channel_idx = -1
        for i, line in enumerate(raw_lines):
            line = line.strip()
            if line.startswith("#EXTINF"):
                current_channel_idx += 1
                channel_vlcopts[current_channel_idx] = {}
            elif line.startswith("#EXTVLCOPT:"):
                # Parse EXTVLCOPT tags
                opt_line = line.replace("#EXTVLCOPT:", "").strip()
                if "=" in opt_line:
                    key, value = opt_line.split("=", 1)
                    key = key.strip().lower()
                    value = value.strip()
                    
                    # Map VLC options to HTTP headers
                    if key == "http-referrer":
                        if current_channel_idx >= 0:
                            if "headers" not in channel_vlcopts[current_channel_idx]:
                                channel_vlcopts[current_channel_idx]["headers"] = {}
                            channel_vlcopts[current_channel_idx]["headers"]["Referer"] = value
                    elif key == "http-user-agent":
                        if current_channel_idx >= 0:
                            if "headers" not in channel_vlcopts[current_channel_idx]:
                                channel_vlcopts[current_channel_idx]["headers"] = {}
                            channel_vlcopts[current_channel_idx]["headers"]["User-Agent"] = value

        content = self._preprocess_m3u_content(raw_content)

        # Pre-process content to ensure #EXTM3U is at the beginning
        extm3u_index = content.find("#EXTM3U")
        if extm3u_index > 0:
            # If #EXTM3U is not at the beginning, trim the content
            content = content[extm3u_index:]
        elif extm3u_index == -1:
            # If #EXTM3U is not found at all, it's an invalid M3U
            logger.error("Error: #EXTM3U tag not found in the playlist content.")
            return []

        try:
            iptv_playlist = playlist.loads(content)
        except Exception as e:
            logger.error(f"Error loading M3U content with ipytv: {e}")
            return []

        channels = []
        date_pattern = re.compile(
            r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b[ -]\d{1,2}[, -]\d{2,4}",
            re.IGNORECASE,
        )
        time_pattern = re.compile(
            r"\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?\s*(?:ET|EST|EDT|UTC)?\s*=?\s*", re.IGNORECASE
        )

        for channel_idx, channel_obj in enumerate(iptv_playlist):
            group_title = channel_obj.attributes.get(IPTVAttr.GROUP_TITLE.value, "Other")
            tvg_name = channel_obj.attributes.get(IPTVAttr.TVG_NAME.value, channel_obj.name)
            if not tvg_name:
                tvg_name = "Unknown Channel"

            is_event = bool(date_pattern.search(tvg_name) and time_pattern.search(tvg_name))
            event_title = None
            event_sport = None
            event_datetime_full = None
            event_team1 = None
            event_team2 = None

            if is_event:
                event_sport = group_title

                event_datetime = self.extract_event_datetime(tvg_name)
                logger.debug(f"Parsing event: {tvg_name}, parsed_datetime: {event_datetime}")
                if event_datetime:
                    # Check if the event is in the past
                    if event_datetime < datetime.now(pytz.utc):
                        continue # Skip to the next channel if the event is in the past
                    event_datetime_full = event_datetime.strftime("%Y-%m-%d %H:%M:%S")
                    
                    # Convert to EST for display
                    est_tz = pytz.timezone("US/Eastern")
                    est_dt = event_datetime.astimezone(est_tz)
                    
                    # Format for display
                    # Converts 'Nov 08 2025 12:00 PM' to 'Nov 08 12:00PM'
                    formatted_dt = est_dt.strftime("%b %d %I:%M%p").replace(" 0", " ").replace(":00", "")
                    
                    # Further clean the event name
                    cleaned_name = re.sub(date_pattern, '', tvg_name).strip()
                    cleaned_name = re.sub(time_pattern, '', cleaned_name).strip()
                    cleaned_name = re.sub(r'^\s*=\s*|\s*=\s*$', '', cleaned_name).strip()

                    # Extract teams and create title
                    team_match = re.search(r"(?P<team1>.*?)\s(?:@|VS)\s(?P<team2>.*)", cleaned_name, re.IGNORECASE)
                    if team_match:
                        event_team1 = team_match.group("team1").strip()
                        event_team2 = team_match.group("team2").strip()
                        event_title = f"{event_team1} @ {event_team2}\n{formatted_dt}"
                    else:
                        event_title = f"{cleaned_name}\n{formatted_dt}"
                else:
                    # Fallback for events without a valid datetime
                    cleaned_name = re.sub(date_pattern, '', tvg_name).strip()
                    cleaned_name = re.sub(time_pattern, '', cleaned_name).strip()
                    cleaned_name = re.sub(r'^\s*=\s*|\s*=\s*$', '', cleaned_name).strip()
                    event_title = cleaned_name
            else:
                event_title = tvg_name # Keep original name if not an event

            # Now generate tvg_id
            tvg_id = channel_obj.attributes.get(IPTVAttr.TVG_ID.value, "")
            if not tvg_id:
                if is_event and event_title and event_datetime_full:
                    unique_identifier = f"{event_title}_{event_datetime_full}"
                    tvg_id = hashlib.sha256(unique_identifier.encode()).hexdigest()
                else:
                    unique_identifier = f"{channel_obj.name}"
                    tvg_id = hashlib.sha256(unique_identifier.encode()).hexdigest()

            tvg_logo = channel_obj.attributes.get(IPTVAttr.TVG_LOGO.value, "") # Change default to empty string

            # If tvg_logo is empty, try to use a static image based on group_title
            if not tvg_logo:
                static_logo_filename = f"{group_title.lower().replace(' ', '-')}.png"
                static_logo_path = os.path.join("static", static_logo_filename)

                # Check if the static file exists in the local filesystem
                # Assuming 'static' directory is at the project root
                if os.path.exists(os.path.join(os.getcwd(), static_logo_path)):
                    tvg_logo = urljoin(HOST_URL, static_logo_path)
                else:
                    tvg_logo = "https://via.placeholder.com/240x135.png?text=No+Logo" # Fallback to generic placeholder

            url_tvg = channel_obj.attributes.get("url-tvg", "")
            stream_url = channel_obj.url
            
            # Get VLC options (HTTP headers) for this channel if available
            stream_headers = None
            if channel_idx in channel_vlcopts and "headers" in channel_vlcopts[channel_idx]:
                stream_headers = channel_vlcopts[channel_idx]["headers"]

            channel_info = {
                "group_title": group_title,
                "tvg_id": tvg_id,
                "tvg_name": tvg_name,
                "tvg_logo": tvg_logo,
                "url_tvg": url_tvg,
                "stream_url": stream_url,
                "stream_headers": stream_headers,  # HTTP headers for stream requests
                "is_event": is_event,
                "event_title": event_title,
                "event_sport": event_sport,
                "event_datetime_full": event_datetime_full,
                "event_team1": event_team1,
                "event_team2": event_team2
            }
            channels.append(channel_info)
        return channels
