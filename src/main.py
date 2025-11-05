import os
import json
import logging
from fastapi import FastAPI, HTTPException, Response, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from datetime import datetime
from dotenv import load_dotenv

from .redis_store import RedisStore
from .models import UserData, ConfigureRequest
from .utils import generate_secret_str, hash_secret_str
from .scheduler import Scheduler

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

app = FastAPI()
redis_store = RedisStore(REDIS_URL)
scheduler = Scheduler()

@app.on_event("startup")
async def startup_event():
    logger.info("FastAPI application startup event triggered.")
    scheduler.start_scheduler()

@app.on_event("shutdown")
async def shutdown_event():
    scheduler.stop_scheduler()

app.mount("/static", StaticFiles(directory="static"), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

async def get_user_data_dependency(secret_str: str) -> UserData:
    user_data = redis_store.get_user_data(secret_str)
    if not user_data:
        raise HTTPException(status_code=404, detail="User configuration not found.")
    return user_data

@app.get("/")
async def root():
    logger.info("Root endpoint accessed.")
    return {"message": "Stremio EyePeaTeaVea Addon"}

@app.post("/configure")
async def configure_addon(
    request: ConfigureRequest
):
    secret_str = generate_secret_str()
    user_data = UserData(
        m3u_sources=request.m3u_sources,
        epg_sources=request.epg_sources,
        parser_schedule_crontab=request.parser_schedule_crontab,
        host_url=request.host_url,
        addon_password=request.addon_password
    )
    redis_store.store_user_data(secret_str, user_data)

    logger.info(f"Triggering immediate M3U fetch for secret_str: {secret_str}")
    scheduler.trigger_m3u_fetch_for_user(secret_str, user_data)
    logger.info(f"Triggering immediate EPG fetch for secret_str: {secret_str}")
    scheduler.trigger_epg_fetch_for_user(secret_str, user_data)

    return {"secret_str": secret_str, "message": "Configuration saved successfully. Use this secret_str in your addon URL."}

@app.get("/{secret_str}/manifest.json")
async def get_manifest(secret_str: str, user_data: UserData = Depends(get_user_data_dependency)):
    logger.info(f"Manifest endpoint accessed for secret_str: {secret_str}")

    # Direct Redis check for 'channels' hash keys
    redis_channel_keys = redis_store.redis_client.hkeys("channels")
    logger.info(f"Direct Redis check - 'channels' hash keys: {redis_channel_keys}")

    all_channels = redis_store.get_all_channels()
    logger.info(f"Retrieved all_channels from Redis: {all_channels}")
    unique_group_titles = set()
    for channel_json in all_channels.values():
        try:
            channel = json.loads(channel_json)
            if "group_title" in channel:
                unique_group_titles.add(channel["group_title"])
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding channel JSON from Redis: {e} - {channel_json}")
    logger.info(f"Unique group titles extracted: {unique_group_titles}")

    manifest = {
        "id": "org.stremio.eyepeateavea",
        "version": "1.0.0",
        "name": "EyePeaTeaVea",
        "description": "Stremio addon for M3U playlists and EPG data",
        "logo": "https://stremio-dev.lynuxss.com/static/logo.png",
        "resources": ["catalog", "meta", "stream"],
        "types": ["tv"],
        "catalogs": [
            {
                "type": "tv",
                "id": "live_tv",
                "name": "IPTV Channels",
                "extra": [
                    {"name": "skip", "isRequired": False},
                    {"name": "genre", "isRequired": False, "options": sorted(list(unique_group_titles))}
                ]
            }
        ]
    }
    return manifest

@app.get("/{secret_str}/catalog/{type}/{id}.json")
@app.get("/{secret_str}/catalog/{type}/{id}/{extra_name}={extra_value}.json")
async def get_catalog(
    secret_str: str,
    type: str,
    id: str,
    user_data: UserData = Depends(get_user_data_dependency),
    extra_name: Optional[str] = None,
    extra_value: Optional[str] = None
):
    if type == "tv" and id == "live_tv":
        channels_data = redis_store.get_all_channels()
        filtered_channels = []

        for tvg_id, channel_json in channels_data.items():
            channel = json.loads(channel_json)

            # Apply genre filter
            if extra_name == "genre" and extra_value:
                if channel.get("group_title") != extra_value:
                    continue

            # Apply search filter (if 'search' extra is implemented)
            # if extra_name == "search" and extra_value:
            #     if extra_value.lower() not in channel.get("tvg_name", "").lower():
            #         continue

            filtered_channels.append(channel)

        metas = []
        for channel in filtered_channels:
            metas.append({
                "id": f"eyepeateavea:{channel['tvg_id']}",
                "type": "tv",
                "name": channel["tvg_name"],
                "poster": channel["tvg_logo"],
                "posterShape": "landscape",
                "background": channel["tvg_logo"],
                "logo": channel["tvg_logo"],
                "description": f"Channel: {channel['tvg_name']} (Group: {channel['group_title']})",
                "genres": [channel["group_title"]],
                "runtime": "",
                "releaseInfo": "",
                "links": [],
                "videos": [
                    {
                        "id": f"eyepeateavea:{channel['tvg_id']}",
                        "title": channel["tvg_name"],
                        "released": datetime.now().strftime("%Y-%m-%d"),
                        "streams": [
                            {
                                "url": channel["stream_url"],
                                "title": "Live"
                            }
                        ]
                    }
                ]
            })
        return {"metas": metas}
    raise HTTPException(status_code=404, detail="Catalog not found")

@app.get("/{secret_str}/meta/{type}/{id}.json")
async def get_meta(secret_str: str, type: str, id: str, user_data: UserData = Depends(get_user_data_dependency)):
    if type == "tv" and id.startswith("eyepeateavea:"):
        tvg_id = id.split(":")[1]
        channel_json = redis_store.get_channel(tvg_id)
        if channel_json:
            channel = json.loads(channel_json)
            meta = {
                "id": f"eyepeateavea:{channel['tvg_id']}",
                "type": "tv",
                "name": channel["tvg_name"],
                "poster": channel["tvg_logo"],
                "posterShape": "landscape",
                "background": channel["tvg_logo"],
                "logo": channel["tvg_logo"],
                "description": f"Channel: {channel['tvg_name']} (Group: {channel['group_title']})",
                "genres": [channel["group_title"]],
                "runtime": "",
                "releaseInfo": "",
                "links": [],
                "videos": [
                    {
                        "id": f"eyepeateavea:{channel['tvg_id']}",
                        "title": channel["tvg_name"],
                        "released": datetime.now().strftime("%Y-%m-%d"),
                        "streams": [
                            {
                                "url": channel["stream_url"],
                                "title": "Live"
                            }
                        ]
                    }
                ]
            }
            return {"meta": meta}
    raise HTTPException(status_code=404, detail="Meta not found")

@app.get("/{secret_str}/stream/{type}/{id}.json")
async def get_stream(secret_str: str, type: str, id: str, user_data: UserData = Depends(get_user_data_dependency)):
    if type == "tv" and id.startswith("eyepeateavea:"):
        tvg_id = id.split(":")[1]
        channel_json = redis_store.get_channel(tvg_id)
        if channel_json:
            channel = json.loads(channel_json)
            stream = {
                "name": channel["tvg_name"],
                "description": f"Live stream for {channel['tvg_name']}",
                "url": channel["stream_url"]
            }
            return {"stream": stream}
    raise HTTPException(status_code=404, detail="Stream not found")
