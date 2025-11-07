import re
import requests
import os
import hashlib
from ipytv import playlist
from ipytv.channel import IPTVAttr
from urllib.parse import urljoin
from dotenv import load_dotenv
from datetime import datetime
import dateparser
import pytz

load_dotenv()

HOST_URL = os.getenv("HOST_URL", "http://localhost:8020")

class M3UParser:
    def __init__(self, m3u_source: str):
        self.m3u_source = m3u_source

    def extract_event_datetime(self, tvg_name: str):
        """
        Extract and parse the most relevant datetime from messy TVG-style event strings.
        Prefers US time zones (EST/EDT > CST/CDT > MST/MDT > PST/PDT > UK/UTC)
        and returns a UTC-aware datetime for consistency.
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
        if s != s_before:

        # 🆕 Handle cases like "UTC HD" or "UTC SD"
        s_before = s
        s = re.sub(r"UTC\s+(HD|SD)\b", "UTC", s)
        if s != s_before:

        # LYNCH
        if re.search(r"\(\d{1,2}:\d{2}", s):
            s = re.sub("\(\d{1,2}:\d{2}", "\(", s)

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
            if s != s_before:

        # 4️⃣ Remove stray characters that confuse parsing
        s_before = s
        s = re.sub(r"[^A-Za-z0-9: \-/]", " ", s)
        if s != s_before:

        # 5️⃣ Parse to datetime
        dt = dateparser.parse(s, settings={'PREFER_DATES_FROM': 'future'})

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
                print(f"Error fetching M3U from {self.m3u_source}: {e}")
                return ""

    def parse(self) -> list[dict]:
        """Parses M3U content using ipytv and extracts channel information."""
        content = self._get_m3u_content()
        if not content:
            return []

        # Pre-process content to ensure #EXTM3U is at the beginning
        extm3u_index = content.find("#EXTM3U")
        if extm3u_index > 0:
            # If #EXTM3U is not at the beginning, trim the content
            content = content[extm3u_index:]
        elif extm3u_index == -1:
            # If #EXTM3U is not found at all, it's an invalid M3U
            print("Error: #EXTM3U tag not found in the playlist content.")
            return []

        try:
            iptv_playlist = playlist.loads(content)
        except Exception as e:
            print(f"Error loading M3U content with ipytv: {e}")
            return []

        channels = []
        date_pattern = re.compile(
            r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b[ -]\d{1,2}[, -]\d{4}",
            re.IGNORECASE,
        )
        time_pattern = re.compile(
            r"\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?\s*(?:ET|EST|EDT|UTC)?\s*=?\s*", re.IGNORECASE
        )

        for channel_obj in iptv_playlist:
            group_title = channel_obj.attributes.get(IPTVAttr.GROUP_TITLE.value, "Other")

            tvg_id = channel_obj.attributes.get(IPTVAttr.TVG_ID.value, "")
            if not tvg_id:
                # Generate a unique tvg_id if not present
                unique_identifier = f"{channel_obj.name}_{channel_obj.url}"
                tvg_id = hashlib.sha256(unique_identifier.encode()).hexdigest()

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
                print(f"Parsing event: {tvg_name}, parsed_datetime: {event_datetime}")
                if event_datetime:
                    # Check if the event is in the past
                    if event_datetime < datetime.now(pytz.utc):
                        continue # Skip to the next channel if the event is in the past
                    event_datetime_full = event_datetime.strftime("%Y-%m-%d %H:%M:%S")

                # Clean the event name by removing date/time and the separator
                cleaned_name = re.sub(date_pattern, '', tvg_name).strip()
                cleaned_name = re.sub(time_pattern, '', cleaned_name).strip()
                # Also remove common separators that might be left over
                cleaned_name = re.sub(r'^\s*=\s*|\s*=\s*$', '', cleaned_name).strip()


                # Extract teams from the cleaned name
                team_match = re.search(r"(?P<team1>.*?)\s(?:@|VS)\s(?P<team2>.*)", cleaned_name, re.IGNORECASE)
                if team_match:
                    event_team1 = team_match.group("team1").strip()
                    event_team2 = team_match.group("team2").strip()
                    event_title = f"{event_team1} @ {event_team2}"
                else:
                    event_title = cleaned_name # Fallback to the cleaned name

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

            channel_info = {
                "group_title": group_title,
                "tvg_id": tvg_id,
                "tvg_name": tvg_name,
                "tvg_logo": tvg_logo,
                "url_tvg": url_tvg,
                "stream_url": stream_url,
                "is_event": is_event,
                "event_title": event_title,
                "event_sport": event_sport,
                "event_datetime_full": event_datetime_full,
                "event_team1": event_team1,
                "event_team2": event_team2
            }
            channels.append(channel_info)
        return channels
