"""
EPG (Electronic Program Guide) parser for XMLTV format files.

This module provides functionality to parse XMLTV EPG files and extract
program schedule information for channels. Supports both compressed (.gz) 
and uncompressed XML files.

The XMLTV format is a standard format for TV program listings.
"""
import gzip
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import pytz
import requests
import os
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

DISABLE_SSL_VERIFY = os.getenv("DISABLE_SSL_VERIFY", "false").lower() == "true"


class EPGParser:
    """
    Parser for XMLTV EPG files.
    
    Parses XMLTV format EPG files from URLs or local files and extracts
    program schedule information. Maps programs to channels using tvg-id.
    
    Attributes:
        epg_url: URL or file path to the EPG file
    """
    
    def __init__(self, epg_url: str):
        self.epg_url = epg_url
    
    def _fetch_epg_content(self) -> bytes:
        """Fetches EPG content from URL or reads from local file."""
        if os.path.exists(self.epg_url):
            with open(self.epg_url, 'rb') as f:
                return f.read()
        else:
            try:
                response = requests.get(
                    self.epg_url, 
                    timeout=30,
                    verify=not DISABLE_SSL_VERIFY
                )
                response.raise_for_status()
                return response.content
            except requests.exceptions.RequestException as e:
                logger.error(f"Error fetching EPG from {self.epg_url}: {e}")
                return b""
    
    def _decompress_if_needed(self, content: bytes) -> bytes:
        """Decompresses gzip content if needed."""
        try:
            # Try to decompress as gzip
            return gzip.decompress(content)
        except (gzip.BadGzipFile, OSError):
            # Not compressed, return as-is
            return content
    
    def _parse_xmltv_datetime(self, dt_str: str) -> Optional[datetime]:
        """
        Parse XMLTV datetime format.
        
        XMLTV format: YYYYMMDDHHMMSS +HHMM or YYYYMMDDHHMMSS
        Examples: "20231222120000 +0000" or "20231222120000"
        """
        try:
            # Remove timezone info if present (we'll handle it separately)
            if ' ' in dt_str:
                dt_part, tz_part = dt_str.split(' ', 1)
            else:
                dt_part = dt_str
                tz_part = None
            
            # Parse datetime: YYYYMMDDHHMMSS
            if len(dt_part) >= 14:
                dt = datetime.strptime(dt_part[:14], "%Y%m%d%H%M%S")
            else:
                return None
            
            # Handle timezone
            if tz_part:
                # Format: +HHMM or -HHMM
                if len(tz_part) == 5:
                    sign = tz_part[0]
                    hours = int(tz_part[1:3])
                    minutes = int(tz_part[3:5])
                    offset = timedelta(hours=hours, minutes=minutes)
                    if sign == '-':
                        offset = -offset
                    # Create timezone-aware datetime
                    tz = pytz.FixedOffset(offset.total_seconds() / 60)
                    dt = tz.localize(dt)
                else:
                    # Default to UTC if timezone format is unexpected
                    dt = pytz.UTC.localize(dt)
            else:
                # Default to UTC if no timezone specified
                dt = pytz.UTC.localize(dt)
            
            return dt
        except (ValueError, AttributeError) as e:
            logger.debug(f"Failed to parse XMLTV datetime '{dt_str}': {e}")
            return None
    
    def parse(self) -> Dict[str, List[Dict]]:
        """
        Parse EPG content and return program schedule by channel.
        
        Returns:
            Dictionary mapping channel tvg-id to list of programs:
            {
                "channel_id": [
                    {
                        "title": "Program Title",
                        "desc": "Program description",
                        "start": datetime object (UTC),
                        "stop": datetime object (UTC),
                        "category": "Category name"
                    },
                    ...
                ],
                ...
            }
        """
        content = self._fetch_epg_content()
        if not content:
            return {}
        
        # Decompress if needed
        content = self._decompress_if_needed(content)
        
        try:
            root = ET.fromstring(content)
        except ET.ParseError as e:
            logger.error(f"Error parsing EPG XML: {e}")
            return {}
        
        # XMLTV namespace - try both with and without namespace
        # Some EPG files don't use namespaces
        ns = {'tv': 'http://www.xmltv.org/ns/0'}
        
        # Check if root has namespace
        if root.tag.startswith('{'):
            # Has namespace
            default_ns = root.tag.split('}')[0][1:]
            ns['tv'] = default_ns
        else:
            # No namespace, use empty namespace
            ns = {'tv': ''}
        
        # Map channel display-name to channel id
        channel_map = {}
        # Try with namespace first, then without
        channel_elements = root.findall('.//tv:channel', ns) if ns.get('tv') else root.findall('.//channel')
        for channel in channel_elements:
            channel_id = channel.get('id')
            if channel_id:
                # Get display name (preferred) or fallback to id
                if ns.get('tv'):
                    display_name = channel.find('tv:display-name', ns)
                else:
                    display_name = channel.find('display-name')
                if display_name is not None and display_name.text:
                    channel_map[channel_id] = display_name.text.strip()
                else:
                    channel_map[channel_id] = channel_id
        
        # Parse programs
        programs_by_channel: Dict[str, List[Dict]] = {}
        now = datetime.now(pytz.UTC)
        
        # Try with namespace first, then without
        programme_elements = root.findall('.//tv:programme', ns) if ns.get('tv') else root.findall('.//programme')
        for programme in programme_elements:
            channel_id = programme.get('channel')
            if not channel_id:
                continue
            
            # Parse start and stop times
            start_str = programme.get('start')
            stop_str = programme.get('stop')
            
            start_dt = self._parse_xmltv_datetime(start_str) if start_str else None
            stop_dt = self._parse_xmltv_datetime(stop_str) if stop_str else None
            
            if not start_dt:
                continue
            
            # Only include current and future programs (up to 30 days ahead for testing)
            # Note: Some EPG files may have programs scheduled far in advance
            if start_dt < now - timedelta(hours=2):  # Skip programs that ended more than 2 hours ago
                continue
            if start_dt > now + timedelta(days=30):  # Skip programs more than 30 days ahead
                continue
            
            # Extract program details
            if ns.get('tv'):
                title_elem = programme.find('tv:title', ns)
                desc_elem = programme.find('tv:desc', ns)
                category_elem = programme.find('tv:category', ns)
            else:
                title_elem = programme.find('title')
                desc_elem = programme.find('desc')
                category_elem = programme.find('category')
            
            title = title_elem.text.strip() if title_elem is not None and title_elem.text else "Unknown"
            desc = desc_elem.text.strip() if desc_elem is not None and desc_elem.text else ""
            category = category_elem.text.strip() if category_elem is not None and category_elem.text else ""
            
            program_data = {
                "title": title,
                "desc": desc,
                "start": start_dt.isoformat(),  # Convert to ISO format string for JSON serialization
                "stop": stop_dt.isoformat() if stop_dt else None,
                "category": category,
                "channel_id": channel_id
            }
            
            # Group by channel
            if channel_id not in programs_by_channel:
                programs_by_channel[channel_id] = []
            
            programs_by_channel[channel_id].append(program_data)
        
        # Sort programs by start time for each channel
        for channel_id in programs_by_channel:
            programs_by_channel[channel_id].sort(key=lambda x: x["start"])
        
        logger.info(f"Parsed EPG: {len(programs_by_channel)} channels, {sum(len(progs) for progs in programs_by_channel.values())} programs")
        
        return programs_by_channel
