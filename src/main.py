"""
FastAPI application for EyePeaTeaVea Stremio addon.

This module defines the main FastAPI application with all API endpoints:
- Configuration endpoints (/configure, /{secret_str}/configure)
- Stremio protocol endpoints (/manifest.json, /catalog, /meta, /stream)
- Image endpoints (/poster, /background, /logo, /icon)
- Health check endpoint (/health)
- Frontend web UI (/frontend)

Features:
- Multi-user support via secret_str
- Rate limiting on configuration endpoint
- CORS configuration for Stremio compatibility
- Automatic M3U playlist fetching and scheduling
"""
import os
import json
import logging
from fastapi import FastAPI, HTTPException, Response, Depends, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from datetime import datetime, timedelta
from dotenv import load_dotenv
from urllib.parse import urljoin

from .redis_store import RedisStore, RedisConnectionError
from .models import UserData, ConfigureRequest, UpdateConfigureRequest
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

# Addon configuration constants
ADDON_ID = os.getenv("ADDON_ID", "org.stremio.eyepeateavea")
ADDON_VERSION = os.getenv("ADDON_VERSION", "1.0.0")
ADDON_NAME = os.getenv("ADDON_NAME", "EyePeaTeaVea")
ADDON_DESCRIPTION = os.getenv("ADDON_DESCRIPTION", "Stremio addon for M3U playlists")
ADDON_ID_PREFIX = os.getenv("ADDON_ID_PREFIX", "eyepeateavea")

# Constants
EVENT_HASH_SUFFIX_LENGTH = 10  # Length of hash suffix used for event unique IDs
SERVICE_NAME = "EyePeaTeaVea"

# Rate limiting constants
RATE_LIMIT_REQUESTS = 10  # Maximum requests per window
RATE_LIMIT_WINDOW_SECONDS = 3600  # Time window in seconds (1 hour)

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

# CORS configuration
# Note: Stremio recommends using "*" for allow_origins because Stremio clients come from
# various origins (web, mobile, smart TV, etc.) and may not send a web-page origin.
# However, we make it configurable for deployments that need stricter security.
cors_allowed_origins_env = os.getenv("CORS_ALLOWED_ORIGINS", "").strip()
if cors_allowed_origins_env:
    if cors_allowed_origins_env == "*":
        # Explicit wildcard
        cors_allowed_origins = ["*"]
        logger.info("CORS configured to allow all origins (*)")
    else:
        # Parse comma-separated list and strip whitespace
        cors_allowed_origins = [origin.strip() for origin in cors_allowed_origins_env.split(",") if origin.strip()]
        logger.info(f"CORS configured with allowed origins: {cors_allowed_origins}")
else:
    # Default: Allow all origins (recommended for Stremio addon compatibility)
    # Stremio clients may come from various origins and may not send a web-page origin
    cors_allowed_origins = ["*"]
    logger.info("CORS using default: allow all origins (*) - recommended for Stremio addon compatibility")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],  # Restrict to needed methods
    allow_headers=["*"],  # Allow all headers (needed for Stremio addon compatibility)
)

def get_client_identifier(request: Request) -> str:
    """Get a unique identifier for rate limiting based on client IP."""
    # Try to get real IP from headers (for proxies/load balancers)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Take the first IP in the chain
        client_ip = forwarded_for.split(",")[0].strip()
    else:
        client_ip = request.client.host if request.client else "unknown"
    
    return f"rate_limit:{client_ip}"

async def rate_limit_dependency(request: Request) -> None:
    """
    Rate limiting dependency for /configure endpoint.
    Limits to RATE_LIMIT_REQUESTS requests per RATE_LIMIT_WINDOW_SECONDS per IP address.
    """
    await check_rate_limit(request, limit=RATE_LIMIT_REQUESTS, window_seconds=RATE_LIMIT_WINDOW_SECONDS)

async def check_rate_limit(
    request: Request,
    limit: int = 10,
    window_seconds: int = 3600
) -> None:
    """
    Rate limiting dependency using Redis sliding window.
    
    Args:
        request: FastAPI request object
        limit: Maximum number of requests allowed in the window (default: 10)
        window_seconds: Time window in seconds (default: 1 hour = 3600s)
        
    Raises:
        HTTPException: If rate limit is exceeded (HTTP 429)
    """
    try:
        client_id = get_client_identifier(request)
        rate_limit_key = f"{client_id}"
        
        # Get current count from Redis
        current_count_bytes = redis_store.get(rate_limit_key)
        
        if current_count_bytes is None:
            # First request in window - initialize counter
            redis_store.set(rate_limit_key, b"1", expiration_time=window_seconds)
            return
        
        # Decode and check count
        try:
            count = int(current_count_bytes.decode('utf-8'))
        except (ValueError, AttributeError):
            # Invalid data, reset counter
            redis_store.set(rate_limit_key, b"1", expiration_time=window_seconds)
            return
        
        if count >= limit:
            logger.warning(f"Rate limit exceeded for {client_id}: {count}/{limit} requests in {window_seconds}s")
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Maximum {limit} requests per {window_seconds // 60} minutes. Please try again later."
            )
        
        # Increment counter (Redis will maintain expiration from first set)
        redis_store.set(rate_limit_key, str(count + 1).encode(), expiration_time=window_seconds)
        
    except HTTPException:
        raise
    except RedisConnectionError:
        # If Redis is unavailable, allow the request but log a warning
        logger.warning("Redis unavailable for rate limiting, allowing request")
        return
    except Exception as e:
        # If rate limiting fails for any reason, log but don't block the request
        logger.error(f"Rate limiting error: {e}")
        return

async def get_user_data_dependency(secret_str: str) -> UserData:
    try:
        user_data = redis_store.get_user_data(secret_str)
        if not user_data:
            raise HTTPException(status_code=404, detail=f"User configuration not found for secret_str: {secret_str}")
        return user_data
    except RedisConnectionError as e:
        logger.error(f"Redis connection error while fetching user data: {e}")
        raise HTTPException(status_code=503, detail="Service temporarily unavailable: Redis connection failed")

@app.get("/")
async def root():
    return FileResponse('frontend/index.html')

@app.get("/health")
async def health_check():
    """Health check endpoint to verify Redis connectivity."""
    try:
        is_connected = redis_store.is_connected()
        if is_connected:
            return {
                "status": "healthy",
                "redis": "connected",
                "service": SERVICE_NAME
            }
        else:
            return {
                "status": "degraded",
                "redis": "disconnected",
                "service": SERVICE_NAME
            }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "redis": "error",
            "service": SERVICE_NAME,
            "error": str(e)
        }

@app.post("/configure", dependencies=[Depends(rate_limit_dependency)])
async def configure_addon(
    request: ConfigureRequest
):
    """Configure a new addon instance. Rate limited to 10 requests per hour per IP."""
    try:
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
    except RedisConnectionError as e:
        logger.error(f"Redis connection error during configuration: {e}")
        raise HTTPException(status_code=503, detail="Service temporarily unavailable: Redis connection failed. Please try again later.")

@app.get("/{secret_str}/config")
async def get_config(secret_str: str, user_data: UserData = Depends(get_user_data_dependency)):
    """Get the current configuration for a user (read-only, for UI purposes)."""
    return {
        "m3u_sources": user_data.m3u_sources,
        "parser_schedule_crontab": user_data.parser_schedule_crontab,
        "host_url": str(user_data.host_url),
        "addon_password": user_data.addon_password
    }

@app.put("/{secret_str}/configure")
@app.patch("/{secret_str}/configure")
async def update_configure_addon(
    secret_str: str,
    request: UpdateConfigureRequest,
    user_data: UserData = Depends(get_user_data_dependency)
):
    """Update an existing user configuration. Only provided fields will be updated."""
    try:
        logger.info(f"Update configuration requested for secret_str: {secret_str}")
        
        # Merge update request with existing user data
        # Only update fields that are provided (not None)
        # For addon_password, empty string means remove password (set to None)
        updated_m3u_sources = request.m3u_sources if request.m3u_sources is not None else user_data.m3u_sources
        updated_crontab = request.parser_schedule_crontab if request.parser_schedule_crontab is not None else user_data.parser_schedule_crontab
        updated_host_url = request.host_url if request.host_url is not None else user_data.host_url
        if request.addon_password is not None:
            # Empty string means remove password, otherwise use the provided value
            updated_password = None if request.addon_password == "" else request.addon_password
        else:
            updated_password = user_data.addon_password
        
        # Create updated user data
        updated_user_data = UserData(
            m3u_sources=updated_m3u_sources,
            parser_schedule_crontab=updated_crontab,
            host_url=updated_host_url,
            addon_password=updated_password
        )
        
        # Store updated configuration
        redis_store.store_user_data(secret_str, updated_user_data)
        
        logger.info(f"Configuration updated for secret_str: {secret_str}")
        logger.info(f"Triggering immediate M3U fetch for secret_str: {secret_str}")
        scheduler.trigger_m3u_fetch_for_user(secret_str, updated_user_data)
        
        # Reload scheduler to update the scheduled job with new cron expression if it changed
        logger.info(f"Reloading scheduler to update configuration for secret_str: {secret_str}")
        scheduler.start_scheduler()
        
        return {
            "secret_str": secret_str,
            "message": "Configuration updated successfully.",
            "updated_fields": {
                "m3u_sources": request.m3u_sources is not None,
                "parser_schedule_crontab": request.parser_schedule_crontab is not None,
                "host_url": request.host_url is not None,
                "addon_password": request.addon_password is not None
            }
        }
    except RedisConnectionError as e:
        logger.error(f"Redis connection error during configuration update: {e}")
        raise HTTPException(status_code=503, detail="Service temporarily unavailable: Redis connection failed. Please try again later.")

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
        channel_name = ADDON_NAME
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
    extra: str | None = None
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
        
        metas = [create_meta(channel, secret_str, ADDON_ID_PREFIX, HOST_URL) for channel in filtered_channels]
        
        return {"metas": metas}

    raise HTTPException(status_code=404, detail=f"Catalog with type: {type} and id: {id} not found.")

@app.get("/{secret_str}/meta/{type}/{id}.json")
async def get_meta(secret_str: str, type: str, id: str, user_data: UserData = Depends(get_user_data_dependency)):
    if type == "events" and id.startswith(f"{ADDON_ID_PREFIX}_event_"):
        parts = id.split('_')
        tvg_id = parts[2]
        event_hash_suffix = parts[3]

        channel_json = redis_store.get_channel(secret_str, tvg_id)
        if channel_json:
            channel = json.loads(channel_json)
            if channel.get("is_event"):
                import hashlib
                current_event_hash_suffix = hashlib.sha256(channel["event_title"].encode()).hexdigest()[:EVENT_HASH_SUFFIX_LENGTH]
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
