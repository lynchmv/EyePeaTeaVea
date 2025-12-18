"""
Catalog utility functions for filtering channels and creating Stremio metadata.

This module provides functions to filter channel data from Redis and create
Stremio-compatible metadata objects for channels and events.
"""
import json
import hashlib
from typing import Any

# Constants
EVENT_HASH_SUFFIX_LENGTH = 10  # Length of hash suffix used for event unique IDs


def filter_channels(
    channels_data: dict[str, str],
    channel_type: str,
    extra_name: str | None = None,
    extra_value: str | None = None,
) -> list[dict[str, Any]]:
    """
    Filter channels based on type and optional extra parameters.
    
    This function filters channels from Redis data based on:
    - Channel type (tv or events)
    - Optional genre filter (for group_title or event_sport)
    - Optional search filter (case-insensitive text search)
    
    Optimized to minimize JSON parsing by parsing each channel only once.
    
    Args:
        channels_data: Dictionary mapping channel IDs to JSON-encoded channel data
        channel_type: Type of channels to filter ("tv" or "events")
        extra_name: Optional filter type ("genre" or "search")
        extra_value: Optional filter value (genre name or search term)
        
    Returns:
        List of filtered channel dictionaries, sorted by name/title
        
    Examples:
        >>> channels = {"CNN": '{"tvg_id": "CNN", "group_title": "News", ...}'}
        >>> filter_channels(channels, "tv")
        [{"tvg_id": "CNN", ...}]
        
        >>> filter_channels(channels, "tv", "genre", "News")
        [{"tvg_id": "CNN", ...}]
        
        >>> filter_channels(channels, "tv", "search", "CNN")
        [{"tvg_id": "CNN", ...}]
    """
    filtered_channels = []
    is_search = extra_name == "search" and extra_value
    search_term_lower = extra_value.lower() if extra_value else None
    
    # Pre-compile filter conditions to avoid repeated checks
    filter_by_genre = extra_name == "genre" and extra_value
    filter_by_search = is_search and search_term_lower

    for _, channel_json in channels_data.items():
        # Parse JSON once per channel
        try:
            channel = json.loads(channel_json)
        except json.JSONDecodeError:
            # Skip invalid JSON
            continue

        # Early filtering based on channel type
        is_event = channel.get("is_event", False)
        
        if channel_type == "tv":
            if is_event:
                continue
            # Apply genre filter if specified
            if filter_by_genre and channel.get("group_title") != extra_value:
                continue
            # Apply search filter if specified
            if filter_by_search:
                tvg_name = channel.get("tvg_name", "")
                if search_term_lower not in tvg_name.lower():
                    continue
        elif channel_type == "events":
            if not is_event:
                continue
            # Apply genre filter if specified
            if filter_by_genre and channel.get("event_sport") != extra_value:
                continue
            # Apply search filter if specified
            if filter_by_search:
                event_title = channel.get("event_title", "")
                if search_term_lower not in event_title.lower():
                    continue
        else:
            continue

        filtered_channels.append(channel)

    # Sort filtered results
    sort_key = "event_title" if channel_type == "events" else "tvg_name"
    filtered_channels.sort(key=lambda x: x.get(sort_key, "").lower())

    return filtered_channels


def create_meta(
    channel: dict[str, Any], 
    secret_str: str, 
    addon_id_prefix: str, 
    host_url: str
) -> dict[str, Any]:
    """
    Create a Stremio-compatible metadata object for a channel or event.
    
    This function generates metadata including:
    - Unique ID based on channel/event type
    - Image URLs (poster, background, logo)
    - Description and genres
    - Type classification (tv or events)
    
    Args:
        channel: Channel dictionary containing channel/event data
        secret_str: User's secret string for URL generation
        addon_id_prefix: Prefix for generating unique IDs (e.g., "eyepeateavea")
        host_url: Base URL for generating image URLs
        
    Returns:
        Dictionary containing Stremio metadata with keys:
        - id: Unique identifier
        - type: "tv" or "events"
        - name: Channel/event name
        - poster: URL to poster image
        - posterShape: "portrait"
        - background: URL to background image
        - logo: URL to logo image
        - description: Channel/event description
        - genres: List of genre strings
        
    Examples:
        >>> channel = {"tvg_id": "CNN", "tvg_name": "CNN", "group_title": "News", ...}
        >>> create_meta(channel, "abc123", "eyepeateavea", "http://localhost:8020")
        {"id": "eyepeateaveaCNN", "type": "tv", "name": "CNN", ...}
    """
    is_event = channel.get("is_event", False)
    channel_type = "events" if is_event else "tv"

    if is_event:
        event_unique_id_suffix = hashlib.sha256(channel["event_title"].encode()).hexdigest()[:EVENT_HASH_SUFFIX_LENGTH]
        meta_id = f"{addon_id_prefix}_event_{channel['tvg_id']}_{event_unique_id_suffix}"
        name = channel["event_title"]
        description = channel["event_title"]
        genres = [channel["event_sport"]]
    else:
        meta_id = f"{addon_id_prefix}{channel['tvg_id']}"
        name = channel["tvg_name"]
        description = f"{channel['tvg_name']}"
        genres = [channel["group_title"]]

    return {
        "id": meta_id,
        "type": channel_type,
        "name": name,
        "poster": f"{host_url}/{secret_str}/poster/{channel['tvg_id']}.png",
        "posterShape": "portrait",
        "background": f"{host_url}/{secret_str}/background/{channel['tvg_id']}.png",
        "logo": f"{host_url}/{secret_str}/logo/{channel['tvg_id']}.png",
        "description": description,
        "genres": genres,
    }
