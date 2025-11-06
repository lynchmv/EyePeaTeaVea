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
        raise HTTPException(status_code=404, detail="User configuration not found.")
    return user_data

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

    return {"secret_str": secret_str, "message": "Configuration saved successfully. Use this secret_str in your addon URL."}

@app.get("/{secret_str}/manifest.json")
async def get_manifest(secret_str: str, user_data: UserData = Depends(get_user_data_dependency)):
    logger.info(f"Manifest endpoint accessed for secret_str: {secret_str}")

    all_channels = redis_store.get_all_channels()
    unique_group_titles = set()
    for channel_json in all_channels.values():
        try:
            channel = json.loads(channel_json)
            if "group_title" in channel:
                unique_group_titles.add(channel["group_title"])
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding channel JSON from Redis: {e} - {channel_json}")

    manifest = {
        "id": "org.stremio.eyepeateavea",
        "version": "1.0.0",
        "name": "EyePeaTeaVea",
        "description": "Stremio addon for M3U playlists",
        "logo": f"{HOST_URL}/{secret_str}/static/logo.png",
        "resources": [
            "catalog",
            {"name": "meta", "types": ["tv"], "idPrefixes": ["eyepeateavea"]},
            {"name": "stream", "types": ["tv"], "idPrefixes": ["eyepeateavea"]}
        ],
        "types": ["tv"],
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
            }
        ]
    }
    return manifest

app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")

@app.get("/{secret_str}/poster/{tvg_id}.png")
async def get_poster_image(secret_str: str, tvg_id: str, user_data: UserData = Depends(get_user_data_dependency)):
    channel_json = redis_store.get_channel(tvg_id)
    if not channel_json:
        raise HTTPException(status_code=404, detail="Channel not found")
    channel = json.loads(channel_json)
    image_url = channel["tvg_logo"]
    processed_image_bytes = await get_poster(redis_store, tvg_id, image_url, channel["tvg_name"])
    if not processed_image_bytes.getvalue():
        raise HTTPException(status_code=404, detail="Image processing failed or image not found")
    return Response(content=processed_image_bytes.getvalue(), media_type="image/jpeg")

@app.get("/{secret_str}/background/{tvg_id}.png")
async def get_background_image(secret_str: str, tvg_id: str, user_data: UserData = Depends(get_user_data_dependency)):
    channel_json = redis_store.get_channel(tvg_id)
    if not channel_json:
        raise HTTPException(status_code=404, detail="Channel not found")
    channel = json.loads(channel_json)
    image_url = channel["tvg_logo"]
    processed_image_bytes = await get_background(redis_store, tvg_id, image_url, channel["tvg_name"])
    if not processed_image_bytes.getvalue():
        raise HTTPException(status_code=404, detail="Image processing failed or image not found")
    return Response(content=processed_image_bytes.getvalue(), media_type="image/jpeg")

@app.get("/{secret_str}/logo/{tvg_id}.png")
async def get_logo_image(secret_str: str, tvg_id: str, user_data: UserData = Depends(get_user_data_dependency)):
    channel_json = redis_store.get_channel(tvg_id)
    if not channel_json:
        raise HTTPException(status_code=404, detail="Channel not found")
    channel = json.loads(channel_json)
    image_url = channel["tvg_logo"]
    processed_image_bytes = await get_logo(redis_store, tvg_id, image_url, channel["tvg_name"])
    if not processed_image_bytes.getvalue():
        raise HTTPException(status_code=404, detail="Image processing failed or image not found")
    return Response(content=processed_image_bytes.getvalue(), media_type="image/jpeg")

@app.get("/{secret_str}/icon/{tvg_id}.png")
async def get_icon_image(secret_str: str, tvg_id: str, user_data: UserData = Depends(get_user_data_dependency)):
    # For the manifest icon, we use a static logo. For channel icons, we use the channel's logo.
    if tvg_id == "logo":
        image_url = f"{HOST_URL}/icon/logo.png"
        channel_name = "EyePeaTeaVea"
    else:
        channel_json = redis_store.get_channel(tvg_id)
        if not channel_json:
            raise HTTPException(status_code=404, detail="Channel not found")
        channel = json.loads(channel_json)
        image_url = channel["tvg_logo"]
        channel_name = channel["tvg_name"]

    processed_image_bytes = await get_icon(redis_store, tvg_id, image_url, channel_name)
    if not processed_image_bytes.getvalue():
        raise HTTPException(status_code=404, detail="Image processing failed or image not found")
    return Response(content=processed_image_bytes.getvalue(), media_type="image/png")

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
    if type == "tv" and id == "iptv_tv":
        channels_data = redis_store.get_all_channels()
        filtered_channels = []

        # Determine if this is a search or a genre filter
        is_search = extra_name == "search" and extra_value

        for tvg_id, channel_json in channels_data.items():
            channel = json.loads(channel_json)

            # Genre filtering
            if extra_name == "genre" and extra_value:
                if channel.get("group_title") != extra_value:
                    continue

            # Search filtering
            if is_search:
                if extra_value.lower() not in channel.get("tvg_name", "").lower():
                    continue

            filtered_channels.append(channel)

        filtered_channels.sort(key=lambda x: x.get("tvg_name", "").lower())

        metas = []
        for channel in filtered_channels:
            meta_obj = {
                "id": f"eyepeateavea{channel['tvg_id']}",
                "type": "tv",
                "name": channel["tvg_name"],
                "poster": f"{HOST_URL}/{secret_str}/poster/{channel['tvg_id']}.png",
                "posterShape": "portrait",
                "background": f"{HOST_URL}/{secret_str}/background/{channel['tvg_id']}.png",
                "logo": f"{HOST_URL}/{secret_str}/logo/{channel['tvg_id']}.png",
                "description": f"Channel: {channel['tvg_name']} (Group: {channel['group_title']})",
                "genres": [channel["group_title"]]
            }

            metas.append(meta_obj)
        return {"metas": metas}
    raise HTTPException(status_code=404, detail="Catalog not found")

@app.get("/{secret_str}/meta/{type}/{id}.json")
async def get_meta(secret_str: str, type: str, id: str, user_data: UserData = Depends(get_user_data_dependency)):
    if type == "tv" and id.startswith("eyepeateavea"):
        tvg_id = id.replace("eyepeateavea", "")
        channel_json = redis_store.get_channel(tvg_id)
        if channel_json:
            channel = json.loads(channel_json)

            meta = {
                "id": f"eyepeateavea{channel['tvg_id']}",
                "type": "tv",
                "name": channel["tvg_name"],
                "poster": f"{HOST_URL}/{secret_str}/poster/{channel['tvg_id']}.png",
                "posterShape": "portrait",
                "background": f"{HOST_URL}/{secret_str}/background/{channel['tvg_id']}.png",
                "logo": f"{HOST_URL}/{secret_str}/logo/{channel['tvg_id']}.png",
                "thumbnail": f"{HOST_URL}/{secret_str}/icon/{channel['tvg_id']}.png",
                "description": f"Channel: {channel['tvg_name']} (Group: {channel['group_title']})",
                "genres": [channel["group_title"]],
                "runtime": "",
                "releaseInfo": "",
                "links": []
            }
            return {"meta": meta}
    raise HTTPException(status_code=404, detail="Meta not found")

@app.get("/{secret_str}/stream/{type}/{id}.json")
async def get_stream(secret_str: str, type: str, id: str, user_data: UserData = Depends(get_user_data_dependency)):
    logger.info(f"Stream endpoint accessed for secret_str: {secret_str}, type: {type}, id: {id}")
    if type == "tv" and id.startswith("eyepeateavea"):
        tvg_id = id.replace("eyepeateavea", "")
        channel_json = redis_store.get_channel(tvg_id)
        if channel_json:
            channel = json.loads(channel_json)
            stream = {
                "name": channel["tvg_name"],
                "description": f"Live stream for {channel['tvg_name']}",
                "url": channel["stream_url"]
            }
            return {"streams": [stream]}
    raise HTTPException(status_code=404, detail="Stream not found")
