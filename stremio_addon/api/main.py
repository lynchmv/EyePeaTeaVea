import logging
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from stremio_addon.core.config import settings
from stremio_addon.db import database, models, crud
from stremio_addon.scheduler.jobs import setup_scheduler
from stremio_addon.core.lock import acquire_scheduler_lock, release_scheduler_lock, maintain_heartbeat

# Configure logging
logging.basicConfig(level=settings.logging_level.upper(), format='%(asctime)s - %(levelname)s - %(message)s')


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handles application startup and shutdown events, ensuring only one
    scheduler instance runs across all worker processes.
    """
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

# --- Start of Correction ---
# Create the FastAPI app instance and pass the lifespan function directly to the constructor.
app = FastAPI(
    title=settings.addon_name,
    version="1.0.0",
    lifespan=lifespan
)
# --- End of Correction ---


@app.get("/manifest.json")
async def get_manifest():
    """
    Provides the manifest file to Stremio, describing the addon's capabilities.
    """
    return {
        "id": "com.my-playlist.addon",
        "version": "1.0.0",
        "name": settings.addon_name,
        "description": "Live TV channels and events from a combined playlist.",
        "logo": settings.logo_url,
        "resources": ["catalog", "stream"],
        "types": ["tv"],
        "catalogs": [
            {
                "type": "tv",
                "id": "regular_channels",
                "name": "TV Channels"
            },
            {
                "type": "tv",
                "id": "live_events",
                "name": "Live Events"
            }
        ],
        "idPrefixes": ["tv_", "event_"]
    }

@app.get("/catalog/{type}/{id}.json")
async def get_catalog(type: str, id: str):
    """
    Provides the content for a specific catalog requested by Stremio.
    """
    metas = []
    if id == "regular_channels":
        channels = await models.MediaFusionTVMetaData.all().to_list()
        for channel in channels:
            metas.append({
                "id": channel.id,
                "name": channel.title,
                "poster": channel.poster or settings.logo_url,
                "type": "tv"
            })
    elif id == "live_events":
        events = await models.MediaFusionEventsMetaData.find().sort("-event_start_timestamp").to_list()
        for event in events:
            metas.append({
                "id": event.id,
                "name": event.title,
                "poster": event.poster or settings.logo_url,
                "type": "tv"
            })

    return {"metas": metas}

@app.get("/stream/{type}/{id}.json")
async def get_stream(type: str, id: str):
    """
    Provides the stream URL for a selected item.
    """
    if id.startswith("tv_"):
        channel = await models.MediaFusionTVMetaData.get(id)
        if channel and channel.streams:
            return {"streams": [{"url": stream.url, "title": stream.name} for stream in channel.streams]}

    elif id.startswith("event_"):
        event = await models.MediaFusionEventsMetaData.get(id)
        if event and event.streams:
            return {"streams": [{"url": stream.url, "title": stream.name} for stream in event.streams]}

    raise HTTPException(status_code=404, detail="Stream not found")

@app.get("/")
async def root():
    """
    Redirects the root URL to the addon's manifest.
    """
    return RedirectResponse(url="/manifest.json")

