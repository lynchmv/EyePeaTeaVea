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
    """
    filtered_channels = []
    is_search = extra_name == "search" and extra_value

    for _, channel_json in channels_data.items():
        channel = json.loads(channel_json)

        if channel_type == "tv":
            if channel.get("is_event"):
                continue
            if extra_name == "genre" and extra_value and channel.get("group_title") != extra_value:
                continue
            if is_search and extra_value.lower() not in channel.get("tvg_name", "").lower():
                continue
        elif channel_type == "events":
            if not channel.get("is_event"):
                continue
            if extra_name == "genre" and extra_value and channel.get("event_sport") != extra_value:
                continue
            if is_search and extra_value.lower() not in channel.get("event_title", "").lower():
                continue
        else:
            continue

        filtered_channels.append(channel)

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
