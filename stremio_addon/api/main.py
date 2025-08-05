import logging
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from io import BytesIO

from stremio_addon.core.config import settings
from stremio_addon.db import database, models
from stremio_addon.scheduler.jobs import setup_scheduler
from stremio_addon.core.lock import acquire_scheduler_lock, release_scheduler_lock, maintain_heartbeat
from stremio_addon.api.security import verify_password
from stremio_addon.utils import poster

# Configure logging
logging.basicConfig(level=settings.logging_level.upper(), format='%(asctime)s - %(levelname)s - %(message)s')


@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.init_db()

    scheduler = None
    lock_id = None

    acquired, lock_id = await acquire_scheduler_lock()
    if acquired:
        try:
            scheduler = AsyncIOScheduler()
            setup_scheduler(scheduler)
            scheduler.start()
            asyncio.create_task(maintain_heartbeat(lock_id))
            logging.info("Scheduler started in this worker process.")
        except Exception as e:
            await release_scheduler_lock(lock_id)
            raise e

    yield

    if scheduler and lock_id:
        scheduler.shutdown()
        await release_scheduler_lock(lock_id)
        logging.info("Scheduler shut down.")

app = FastAPI(
    title=settings.addon_name,
    version="1.0.0",
    lifespan=lifespan
)

app.mount("/static", StaticFiles(directory="stremio_addon/static"), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    password_segment = f"/{settings.addon_password}" if settings.addon_password else ""
    return RedirectResponse(url=f"{password_segment}/manifest.json")

@app.get("/manifest.json")
@app.get("/{password}/manifest.json")
async def get_manifest(password_check: None = Depends(verify_password)):
    """
    Provides a dynamic manifest structured correctly for TV and Events.
    """
    catalogs = []

    try:
        # 1. Get TV Channel genres and create the TV catalog
        channel_genres = await models.MediaFusionTVMetaData.distinct("genres")
        if channel_genres:
            catalogs.append({
                "type": "tv",
                "id": "tv_channels",
                "name": "Live TV Channels",
                "extra": [{"name": "genre", "options": sorted(channel_genres)}]
            })

        # 2. Get Live Event genres and create the Events catalog
        event_genres = await models.MediaFusionEventsMetaData.distinct("genres")
        if event_genres:
            catalogs.append({
                "type": "events",
                "id": "live_events",
                "name": "Live TV Events",
                "extra": [{"name": "genre", "options": sorted(event_genres)}]
            })
    except Exception as e:
        logging.error(f"Could not fetch genres for manifest: {e}")

    return {
        "id": "stremio.addons.eyepeateavea",
        "version": "1.0.0",
        "name": settings.addon_name,
        "description": "Live TV channels and events from user curated playlists.",
        "logo": settings.logo_url,
        "resources": ["catalog", "stream"],
        "types": ["tv", "events"], # Add "events" as a supported type
        "catalogs": catalogs,
        "idPrefixes": ["tv_", "event_"]
    }

@app.get("/catalog/{type}/{id}.json")
@app.get("/catalog/{type}/{id}/genre={genre}.json")
@app.get("/{password}/catalog/{type}/{id}.json")
@app.get("/{password}/catalog/{type}/{id}/genre={genre}.json")
async def get_catalog(type: str, id: str, genre: str = None, password_check: None = Depends(verify_password)):
    metas = []

    if type == "tv":
        query = {}
        if genre:
            query["genres"] = genre
        channels = await models.MediaFusionTVMetaData.find(query).to_list()
        for channel in channels:
            metas.append({
                "id": channel.id,
                "name": channel.title,
                "poster": f"{settings.host_url}/poster/tv/{channel.id}.jpg",
                "type": "tv"
            })

    elif type == "events":
        query = {}
        if genre:
            query["genres"] = genre
        events = await models.MediaFusionEventsMetaData.find(query).sort("-event_start_timestamp").to_list()
        for event in events:
            metas.append({
                "id": event.id,
                "name": event.title,
                "poster": f"{settings.host_url}/poster/event/{event.id}.jpg",
                "type": "events" # Corrected type from "tv" to "events"
            })

    return {"metas": metas}

@app.get("/stream/{type}/{id}.json")
@app.get("/{password}/stream/{type}/{id}.json")
async def get_stream(type: str, id: str, password_check: None = Depends(verify_password)):
    if id.startswith("tv_"):
        item = await models.MediaFusionTVMetaData.get(id)
    elif id.startswith("event_"):
        item = await models.MediaFusionEventsMetaData.get(id)
    else:
        item = None

    if item and item.streams:
        return {"streams": [{"url": stream.url, "title": stream.name} for stream in item.streams]}

    raise HTTPException(status_code=404, detail="Stream not found")

@app.get("/poster/{type}/{id}.jpg")
async def get_poster(type: str, id: str):
    if type == "tv":
        media_data = await models.MediaFusionTVMetaData.get(id)
    elif type == "event":
        media_data = await models.MediaFusionEventsMetaData.get(id)
    else:
        media_data = None

    if not media_data or not media_data.poster:
        raise HTTPException(status_code=404, detail="Poster not found.")

    try:
        image_bytes_io = await poster.create_poster(media_data)
        return StreamingResponse(image_bytes_io, media_type="image/jpeg")
    except Exception as e:
        logging.error(f"Failed to create poster for {id}: {e}")
        return RedirectResponse(url=settings.logo_url)

