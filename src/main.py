import os
import json
import logging
from fastapi import FastAPI, HTTPException, Response, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from typing import Optional
from datetime import datetime
from dotenv import load_dotenv
from urllib.parse import urljoin

from .redis_store import RedisStore
from .models import UserData, ConfigureRequest
from .utils import generate_secret_str, hash_secret_str
from .scheduler import Scheduler
from .image_processor import get_poster, get_background, get_logo, get_icon
from .catalog_utils import filter_channels, create_meta

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from contextlib import asynccontextmanager

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
HOST_URL = os.getenv("HOST_URL", "http://localhost:8020")

redis_store = RedisStore(REDIS_URL)
scheduler = Scheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("FastAPI application startup event triggered.")
    scheduler.start_scheduler()
    try:
        yield
    finally:
        scheduler.stop_scheduler()
        logger.info("FastAPI application shutdown event triggered.")

app = FastAPI(lifespan=lifespan)

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
        raise HTTPException(status_code=404, detail=f"User configuration not found for secret_str: {secret_str}")
    return user_data

@app.get("/")
async def root():
    return FileResponse('frontend/index.html')

@app.post("/configure")
async def configure_addon(
    request: ConfigureRequest
):
    secret_str = generate_secret_str()
    user_data = UserData(
        m3u_sources=request.m3u_sources,
        parser_schedule_crontab=request.parser_schedule_crontab,
        host_url=request.host_url,
        addon_password=request.addon_password
    )
    redis_store.store_user_data(secret_str, user_data)

    logger.info(f"Triggering immediate M3U fetch for secret_str: {secret_str}")
    scheduler.trigger_m3u_fetch_for_user(secret_str, user_data)
    
    # Reload scheduler to include the new user's scheduled job
    logger.info(f"Reloading scheduler to include new configuration for secret_str: {secret_str}")
    scheduler.start_scheduler()

    return {"secret_str": secret_str, "message": "Configuration saved successfully. Use this secret_str in your addon URL."}

@app.get("/{secret_str}/manifest.json")
async def get_manifest(secret_str: str, user_data: UserData = Depends(get_user_data_dependency)):
    logger.info(f"Manifest endpoint accessed for secret_str: {secret_str}")

    all_channels = redis_store.get_all_channels(secret_str)
    unique_group_titles = set()
    unique_event_genres = set()
    for channel_json in all_channels.values():
        try:
            channel = json.loads(channel_json)
            if "group_title" in channel:
                if not channel.get("is_event"):
                    unique_group_titles.add(channel["group_title"])
            if channel.get("is_event") and channel.get("event_sport"):
                unique_event_genres.add(channel["event_sport"])
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding channel JSON from Redis: {e} - {channel_json}")

    ADDON_ID = os.getenv("ADDON_ID", "org.stremio.eyepeateavea")
    ADDON_VERSION = os.getenv("ADDON_VERSION", "1.0.0")
    ADDON_NAME = os.getenv("ADDON_NAME", "EyePeaTeaVea")
    ADDON_DESCRIPTION = os.getenv("ADDON_DESCRIPTION", "Stremio addon for M3U playlists")
    ADDON_ID_PREFIX = os.getenv("ADDON_ID_PREFIX", "eyepeateavea")

    manifest = {
        "id": ADDON_ID,
        "version": ADDON_VERSION,
        "name": ADDON_NAME,
        "description": ADDON_DESCRIPTION,
        "logo": f"{HOST_URL}/static/logo.png",
        "resources": [
            "catalog",
            {"name": "meta", "types": ["tv", "events"], "idPrefixes": [ADDON_ID_PREFIX]},
            {"name": "stream", "types": ["tv", "events"], "idPrefixes": [ADDON_ID_PREFIX]}
        ],
        "types": ["tv", "events"],
        "catalogs": [
            {
                "type": "tv",
                "id": "iptv_tv",
                "name": "IPTV Channels",
                "extra": [
                    {"name": "skip", "isRequired": False},
                    {"name": "genre", "isRequired": False, "options": sorted(list(unique_group_titles))},
                    {"name": "search", "isRequired": False}
                ]
            },
            {
                "type": "events",
                "id": "iptv_sports_events",
                "name": "IPTV Sports Events",
                "extra": [
                    {"name": "skip", "isRequired": False},
                    {"name": "genre", "isRequired": False, "options": sorted(list(unique_event_genres))}
                ]
            }
        ]
    }
    return manifest

app.mount("/frontend", StaticFiles(directory="frontend", html=True), name="frontend")

@app.get("/{secret_str}/poster/{tvg_id}.png")
async def get_poster_image(secret_str: str, tvg_id: str, user_data: UserData = Depends(get_user_data_dependency)):
    channel_json = redis_store.get_channel(secret_str, tvg_id)
    if not channel_json:
        raise HTTPException(status_code=404, detail=f"Channel with tvg_id: {tvg_id} not found.")
    channel = json.loads(channel_json)
    image_url = channel["tvg_logo"]
    processed_image_bytes = await get_poster(redis_store, tvg_id, image_url, channel["tvg_name"])
    if not processed_image_bytes.getvalue():
        raise HTTPException(status_code=500, detail=f"Image processing failed for tvg_id: {tvg_id}")
    return Response(content=processed_image_bytes.getvalue(), media_type="image/jpeg")

@app.get("/{secret_str}/background/{tvg_id}.png")
async def get_background_image(secret_str: str, tvg_id: str, user_data: UserData = Depends(get_user_data_dependency)):
    channel_json = redis_store.get_channel(secret_str, tvg_id)
    if not channel_json:
        raise HTTPException(status_code=404, detail=f"Channel with tvg_id: {tvg_id} not found.")
    channel = json.loads(channel_json)
    image_url = channel["tvg_logo"]
    processed_image_bytes = await get_background(redis_store, tvg_id, image_url, channel["tvg_name"])
    if not processed_image_bytes.getvalue():
        raise HTTPException(status_code=500, detail=f"Image processing failed for tvg_id: {tvg_id}")
    return Response(content=processed_image_bytes.getvalue(), media_type="image/jpeg")

@app.get("/{secret_str}/logo/{tvg_id}.png")
async def get_logo_image(secret_str: str, tvg_id: str, user_data: UserData = Depends(get_user_data_dependency)):
    channel_json = redis_store.get_channel(secret_str, tvg_id)
    if not channel_json:
        raise HTTPException(status_code=404, detail=f"Channel with tvg_id: {tvg_id} not found.")
    channel = json.loads(channel_json)
    image_url = channel["tvg_logo"]
    processed_image_bytes = await get_logo(redis_store, tvg_id, image_url, channel["tvg_name"])
    if not processed_image_bytes.getvalue():
        raise HTTPException(status_code=500, detail=f"Image processing failed for tvg_id: {tvg_id}")
    return Response(content=processed_image_bytes.getvalue(), media_type="image/jpeg")

@app.get("/{secret_str}/icon/{tvg_id}.png")
async def get_icon_image(secret_str: str, tvg_id: str, user_data: UserData = Depends(get_user_data_dependency)):
    # For the manifest icon, we use a static logo. For channel icons, we use the channel's logo.
    if tvg_id == "logo":
        image_url = f"{HOST_URL}/icon/logo.png"
        channel_name = os.getenv("ADDON_NAME", "EyePeaTeaVea")
    else:
        channel_json = redis_store.get_channel(secret_str, tvg_id)
        if not channel_json:
            raise HTTPException(status_code=404, detail=f"Channel with tvg_id: {tvg_id} not found.")
        channel = json.loads(channel_json)
        image_url = channel["tvg_logo"]
        channel_name = channel["tvg_name"]

    processed_image_bytes = await get_icon(redis_store, tvg_id, image_url, channel_name)
    if not processed_image_bytes.getvalue():
        raise HTTPException(status_code=500, detail=f"Image processing failed for tvg_id: {tvg_id}")
    return Response(content=processed_image_bytes.getvalue(), media_type="image/png")

@app.get("/{secret_str}/catalog/{type}/{id}.json")
@app.get("/{secret_str}/catalog/{type}/{id}/{extra:path}.json")
async def get_catalog(
    secret_str: str,
    type: str,
    id: str,
    user_data: UserData = Depends(get_user_data_dependency),
    extra: Optional[str] = None
):
    extra_name = None
    extra_value = None
    if extra:
        parts = extra.split('=', 1)
        if len(parts) == 2:
            extra_name = parts[0]
            extra_value = parts[1]

    if (type == "tv" and id == "iptv_tv") or (type == "events" and id == "iptv_sports_events"):
        channels_data = redis_store.get_all_channels(secret_str)
        if not channels_data:
            return {"metas": []}
            
        filtered_channels = filter_channels(channels_data, type, extra_name, extra_value)
        
        ADDON_ID_PREFIX = os.getenv("ADDON_ID_PREFIX", "eyepeateavea")
        HOST_URL = os.getenv("HOST_URL", "http://localhost:8020")
        
        metas = [create_meta(channel, secret_str, ADDON_ID_PREFIX, HOST_URL) for channel in filtered_channels]
        
        return {"metas": metas}

    raise HTTPException(status_code=404, detail=f"Catalog with type: {type} and id: {id} not found.")

@app.get("/{secret_str}/meta/{type}/{id}.json")
async def get_meta(secret_str: str, type: str, id: str, user_data: UserData = Depends(get_user_data_dependency)):
    ADDON_ID_PREFIX = os.getenv("ADDON_ID_PREFIX", "eyepeateavea")
    HOST_URL = os.getenv("HOST_URL", "http://localhost:8020")

    if type == "events" and id.startswith(f"{ADDON_ID_PREFIX}_event_"):
        parts = id.split('_')
        tvg_id = parts[2]
        event_hash_suffix = parts[3]

        channel_json = redis_store.get_channel(secret_str, tvg_id)
        if channel_json:
            channel = json.loads(channel_json)
            if channel.get("is_event"):
                import hashlib
                current_event_hash_suffix = hashlib.sha256(channel["event_title"].encode()).hexdigest()[:10]
                if current_event_hash_suffix == event_hash_suffix:
                    meta = create_meta(channel, secret_str, ADDON_ID_PREFIX, HOST_URL)
                    meta.update({"runtime": "", "releaseInfo": "", "links": []})
                    return {"meta": meta}
    elif type == "tv" and id.startswith(ADDON_ID_PREFIX):
        tvg_id = id.replace(ADDON_ID_PREFIX, "")
        channel_json = redis_store.get_channel(secret_str, tvg_id)
        if channel_json:
            channel = json.loads(channel_json)
            if not channel.get("is_event"):
                meta = create_meta(channel, secret_str, ADDON_ID_PREFIX, HOST_URL)
                meta.update({"runtime": "", "releaseInfo": "", "links": []})
                return {"meta": meta}
    raise HTTPException(status_code=404, detail=f"Meta with type: {type} and id: {id} not found.")

@app.get("/{secret_str}/stream/{type}/{id}.json")
async def get_stream(secret_str: str, type: str, id: str, user_data: UserData = Depends(get_user_data_dependency)):
    logger.info(f"Stream endpoint accessed for secret_str: {secret_str}, type: {type}, id: {id}")
    
    ADDON_ID_PREFIX = os.getenv("ADDON_ID_PREFIX", "eyepeateavea")

    if (type == "tv" or type == "events") and (id.startswith(f"{ADDON_ID_PREFIX}_event_") or id.startswith(ADDON_ID_PREFIX)):
        if id.startswith(f"{ADDON_ID_PREFIX}_event_"):
            parts = id.split('_')
            tvg_id = parts[2]
        else:
            tvg_id = id.replace(ADDON_ID_PREFIX, "")
        channel_json = redis_store.get_channel(secret_str, tvg_id)
        if channel_json:
            channel = json.loads(channel_json)
            name = channel["event_title"] if channel.get("is_event") else channel["tvg_name"]
            stream = {
                "name": name,
                "description": f"Live stream for {name}",
                "url": channel["stream_url"]
            }
            return {"streams": [stream]}
    raise HTTPException(status_code=404, detail=f"Stream with type: {type} and id: {id} not found.")
