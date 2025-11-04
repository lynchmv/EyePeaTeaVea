import os
import json
import logging
from fastapi import FastAPI, HTTPException, Response
from dotenv import load_dotenv

from redis_store import RedisStore

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
HOST_URL = os.getenv("HOST_URL", "http://localhost:8020")
ADDON_PASSWORD = os.getenv("ADDON_PASSWORD")

app = FastAPI()
redis_store = RedisStore(REDIS_URL)

@app.get("/")
async def root():
    logger.info("Root endpoint accessed.")
    return {"message": "Stremio EyePeaTeaVea Addon"}

@app.get("/manifest.json")
async def get_manifest():
    logger.info("Manifest endpoint accessed.")
    manifest = {
        "id": "org.stremio.eyepeateavea",
        "version": "1.0.0",
        "name": "EyePeaTeaVea",
        "description": "Dynamic M3U and EPG Stremio Addon",
        "resources": [
            "catalog",
            "meta",
            "stream"
        ],
        "types": [
            "tv"
        ],
        "catalogs": [
            {
                "type": "tv",
                "id": "eyepeateavea_channels",
                "name": "EyePeaTeaVea Channels",
                "extra": [
                    {"name": "search", "isRequired": False}
                ]
            }
        ],
        "behaviorHints": {
            "configurable": True,
            "configurationRequired": False
        }
    }
    return manifest

@app.get("/catalog/{type}/{id}.json")
async def get_catalog(type: str, id: str):
    if type == "tv" and id == "eyepeateavea_channels":
        channels_data = redis_store.get_all_channels()
        metas = []
        for tvg_id, channel_json in channels_data.items():
            channel = json.loads(channel_json)
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
                "videos": []
            })
        return {"metas": metas}
    raise HTTPException(status_code=404, detail="Catalog not found")

@app.get("/meta/{type}/{id}.json")
async def get_meta(type: str, id: str):
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
                "videos": []
            }
            return {"meta": meta}
    raise HTTPException(status_code=404, detail="Meta not found")

@app.get("/stream/{type}/{id}.json")
async def get_stream(type: str, id: str):
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
