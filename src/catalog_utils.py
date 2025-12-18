import json
import hashlib
from typing import List, Dict, Optional



def filter_channels(
    channels_data: Dict[str, str],
    channel_type: str,
    extra_name: Optional[str] = None,
    extra_value: Optional[str] = None,
) -> List[Dict]:
    """
    Filters channels based on type and extra parameters.
    Optimized to minimize JSON parsing and improve performance.
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


def create_meta(channel: Dict, secret_str: str, addon_id_prefix: str, host_url: str) -> Dict:
    """
    Creates a meta object for a channel.
    """
    is_event = channel.get("is_event", False)
    channel_type = "events" if is_event else "tv"

    if is_event:
        event_unique_id_suffix = hashlib.sha256(channel["event_title"].encode()).hexdigest()[:10]
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
