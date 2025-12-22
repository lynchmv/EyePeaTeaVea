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
import hashlib
from fastapi import FastAPI, HTTPException, Response, Depends, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from datetime import datetime, timedelta
import pytz
from dotenv import load_dotenv
from urllib.parse import urljoin

from .redis_store import RedisStore, RedisConnectionError
from .models import UserData, ConfigureRequest, UpdateConfigureRequest
from .utils import generate_secret_str, hash_secret_str, validate_secret_str, hash_password, validate_url
from .scheduler import Scheduler
from .image_processor import get_poster, get_background, get_logo, get_icon, close_http_client, GENERIC_PLACEHOLDER_URL
from .catalog_utils import filter_channels, create_meta, create_empty_meta

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

def validate_configuration() -> None:
    """
    Validate application configuration at startup.

    Checks that required environment variables are set and valid.
    Raises ValueError if configuration is invalid.
    """
    errors = []

    # Validate Redis URL
    if not REDIS_URL:
        errors.append("REDIS_URL is not set")
    elif not REDIS_URL.startswith(("redis://", "rediss://")):
        errors.append(f"REDIS_URL must start with redis:// or rediss://, got: {REDIS_URL}")

    # Validate HOST_URL
    if not HOST_URL:
        errors.append("HOST_URL is not set")
    else:
        try:
            validate_url(HOST_URL)
        except ValueError as e:
            errors.append(f"Invalid HOST_URL: {e}")

    # Validate addon configuration (warn but don't fail)
    if not ADDON_ID:
        logger.warning("ADDON_ID is not set, using default")
    if not ADDON_NAME:
        logger.warning("ADDON_NAME is not set, using default")

    if errors:
        error_msg = "Configuration validation failed:\n" + "\n".join(f"  - {error}" for error in errors)
        logger.error(error_msg)
        raise ValueError(error_msg)

    logger.info("Configuration validation passed")

redis_store = RedisStore(REDIS_URL)
scheduler = Scheduler()

# Validate configuration at module load time
try:
    validate_configuration()
except ValueError as e:
    logger.error(f"Startup configuration error: {e}")
    # Don't raise here - let the application start and fail gracefully if needed

@asynccontextmanager
async def lifespan(app: FastAPI):
    import os  # Import os module for this function
    logger.info("FastAPI application startup event triggered.")
    
    # Log local tv-logos repository status
    tv_logos_path = os.getenv("TV_LOGOS_REPO_PATH", "").strip()
    if tv_logos_path:
        if os.path.exists(tv_logos_path) and os.path.isdir(tv_logos_path):
            test_file = os.path.join(tv_logos_path, "countries")
            if os.path.exists(test_file):
                logger.info(f"✓ Local tv-logos repository is available at: {tv_logos_path}")
            else:
                logger.warning(f"⚠ TV_LOGOS_REPO_PATH set to '{tv_logos_path}' but repository structure incomplete (missing 'countries' directory)")
        else:
            logger.warning(f"⚠ TV_LOGOS_REPO_PATH set to '{tv_logos_path}' but directory does not exist")
    else:
        logger.info("ℹ Local tv-logos repository disabled (TV_LOGOS_REPO_PATH not set)")
    
    scheduler.start_scheduler()
    try:
        yield
    finally:
        scheduler.stop_scheduler()
        await close_http_client()  # Clean up HTTP client connections
        logger.info("FastAPI application shutdown event triggered.")

app = FastAPI(
    title=ADDON_NAME,
    description=ADDON_DESCRIPTION,
    version=ADDON_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

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

# Add compression middleware for better performance
app.add_middleware(GZipMiddleware, minimum_size=1000)

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
    Rate limiting dependency using Redis atomic INCR operation.

    Uses Redis INCR for atomic counter increments, ensuring thread-safe
    rate limiting even under high concurrency.

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

        # Atomically increment counter using Redis INCR
        # This ensures thread-safe counting even under high concurrency
        count = redis_store.incr(rate_limit_key, expiration_time=window_seconds)

        if count > limit:
            logger.warning(f"Rate limit exceeded for {client_id}: {count}/{limit} requests in {window_seconds}s")
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Maximum {limit} requests per {window_seconds // 60} minutes. Please try again later."
            )

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
    """
    Dependency function to validate secret_str and retrieve user data.

    Validates the secret_str format and retrieves user configuration from Redis.
    Raises appropriate HTTP exceptions for invalid or missing configurations.

    Args:
        secret_str: User's secret string (validated)

    Returns:
        UserData instance for the user

    Raises:
        HTTPException: 400 if secret_str is invalid, 404 if not found, 503 if Redis unavailable
    """
    try:
        # Validate secret_str format
        validate_secret_str(secret_str)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid secret_str: {e}")

    try:
        user_data = redis_store.get_user_data(secret_str)
        if not user_data:
            raise HTTPException(
                status_code=404, 
                detail=f"Configuration not found. Please check your secret_str or configure a new addon at {HOST_URL}/configure"
            )
        return user_data
    except RedisConnectionError as e:
        logger.error(f"Redis connection error while fetching user data: {e}")
        raise HTTPException(
            status_code=503, 
            detail="Service temporarily unavailable: Database connection failed. Please try again in a few moments."
        )

def get_channel_data(secret_str: str, tvg_id: str) -> dict:
    """
    Retrieve and parse channel data from Redis.

    Args:
        secret_str: User's secret string
        tvg_id: Channel identifier

    Returns:
        Parsed channel dictionary

    Raises:
        HTTPException: If channel not found or JSON parsing fails
    """
    channel_json = redis_store.get_channel(secret_str, tvg_id)
    if not channel_json:
        raise HTTPException(
            status_code=404, 
            detail=f"Channel not found. The channel may have been removed or the playlist may need to be refreshed. Try updating your configuration at {HOST_URL}/{secret_str}/configure"
        )

    try:
        return json.loads(channel_json)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse channel JSON for tvg_id {tvg_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Invalid channel data for tvg_id: {tvg_id}")

async def get_image_response(
    secret_str: str,
    tvg_id: str,
    image_processor_func,
    media_type: str = "image/png"
) -> Response:
    """
    Common helper function for image endpoints.

    Args:
        secret_str: User's secret string
        tvg_id: Channel identifier
        image_processor_func: Async function to process the image (get_poster, get_background, etc.)
        media_type: MIME type for the response

    Returns:
        FastAPI Response with image content

    Raises:
        HTTPException: If channel not found or image processing fails
    """
    # Handle empty placeholder images
    if tvg_id == "empty_placeholder":
        # Generate placeholder image with appropriate title based on context
        # We'll use a generic message since we don't know the type here
        title = "No Content Available"
        processed_image_bytes = await image_processor_func(redis_store, tvg_id, GENERIC_PLACEHOLDER_URL, title)
    else:
        channel = get_channel_data(secret_str, tvg_id)
        image_url = channel["tvg_logo"]
        # Use parsed event_title if available (for events), otherwise use tvg_name
        if channel.get("is_event") and channel.get("event_title"):
            title = channel["event_title"]
            # For logos, use just the first line (before newline) to keep it shorter
            if "\n" in title:
                title = title.split("\n")[0]
        else:
            title = channel["tvg_name"]

        processed_image_bytes = await image_processor_func(redis_store, tvg_id, image_url, title)
    if not processed_image_bytes.getvalue():
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to generate image for this channel. This may be a temporary issue - please try again later."
        )

    return Response(content=processed_image_bytes.getvalue(), media_type=media_type)

@app.get("/")
async def root():
    return FileResponse('frontend/index.html')

@app.get("/{secret_str}/configure")
async def configure_page(secret_str: str):
    """
    Serve the configuration page with the secret_str pre-filled and in update mode.
    This allows users to access /{secret_str}/configure directly to update their configuration.
    
    Always returns the HTML page, even if the secret_str doesn't exist.
    The frontend will handle displaying an appropriate error message when it tries to load the config.
    """
    # Validate secret_str format only (don't check if it exists - let frontend handle that)
    try:
        validate_secret_str(secret_str)
    except ValueError:
        # Invalid format - still return HTML page, frontend will show error when trying to load
        pass
    
    # Always return the frontend page - the frontend will detect the secret_str in the URL
    # and attempt to auto-load. If the secret_str doesn't exist, the frontend will show an error.
    return FileResponse('frontend/index.html')

@app.get("/health")
async def health_check():
    """
    Health check endpoint with comprehensive status information.

    Returns detailed health status including:
    - Overall service status
    - Redis connectivity and metrics
    - Configuration status
    - Service metadata
    - User and channel statistics
    """
    health_status = {
        "status": "healthy",
        "service": SERVICE_NAME,
        "version": ADDON_VERSION,
        "timestamp": datetime.now().isoformat(),
        "checks": {}
    }

    # Check Redis connectivity
    try:
        is_connected = redis_store.is_connected()
        if is_connected:
            # Try a simple operation to verify Redis is actually working
            try:
                redis_store.redis_client.ping()
                
                # Get some metrics
                try:
                    total_users = len(redis_store.get_all_secret_strs())
                    # Count total channels (approximate - count keys)
                    channel_keys = list(redis_store.redis_client.scan_iter(match="channel:*"))
                    total_channels = len(channel_keys)
                except Exception:
                    total_users = None
                    total_channels = None
                
                health_status["checks"]["redis"] = {
                    "status": "healthy",
                    "connected": True,
                    "url": REDIS_URL.split("@")[-1] if "@" in REDIS_URL else REDIS_URL,  # Hide credentials
                    "metrics": {
                        "total_users": total_users,
                        "total_channels": total_channels
                    }
                }
            except Exception as e:
                health_status["checks"]["redis"] = {
                    "status": "degraded",
                    "connected": False,
                    "error": str(e)
                }
                health_status["status"] = "degraded"
        else:
            health_status["checks"]["redis"] = {
                "status": "unhealthy",
                "connected": False
            }
            health_status["status"] = "degraded"
    except Exception as e:
        health_status["checks"]["redis"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        health_status["status"] = "unhealthy"

    # Check configuration
    try:
        config_valid = True
        config_errors = []

        if not REDIS_URL:
            config_valid = False
            config_errors.append("REDIS_URL not set")
        if not HOST_URL:
            config_valid = False
            config_errors.append("HOST_URL not set")

        health_status["checks"]["configuration"] = {
            "status": "healthy" if config_valid else "degraded",
            "valid": config_valid
        }
        if config_errors:
            health_status["checks"]["configuration"]["errors"] = config_errors
            if health_status["status"] == "healthy":
                health_status["status"] = "degraded"
    except Exception as e:
        health_status["checks"]["configuration"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        health_status["status"] = "unhealthy"

    return health_status

@app.post("/configure", dependencies=[Depends(rate_limit_dependency)])
async def configure_addon(
    request: ConfigureRequest
):
    """
    Configure a new addon instance. Rate limited to 10 requests per hour per IP.
    
    Creates a new Stremio addon configuration with M3U playlist sources and scheduling.
    Returns a secret_str that should be used in the addon URL.
    """
    try:
        secret_str = generate_secret_str()
        # Hash password before storage if provided
        hashed_password = hash_password(request.addon_password) if request.addon_password else None
        user_data = UserData(
            m3u_sources=request.m3u_sources,
            parser_schedule_crontab=request.parser_schedule_crontab,
            host_url=request.host_url,
            addon_password=hashed_password
        )
        redis_store.store_user_data(secret_str, user_data)
        
        # Invalidate manifest cache when configuration changes
        redis_store.redis_client.delete(f"manifest:{secret_str}")

        logger.info(f"Triggering immediate M3U fetch for secret_str: {secret_str[:8]}...")
        scheduler.trigger_m3u_fetch_for_user(secret_str, user_data)

        # Reload scheduler to include the new user's scheduled job
        logger.info(f"Reloading scheduler to include new configuration for secret_str: {secret_str[:8]}...")
        scheduler.start_scheduler()

        return {"secret_str": secret_str, "message": "Configuration saved successfully. Use this secret_str in your addon URL."}
    except RedisConnectionError as e:
        logger.error(f"Redis connection error during configuration: {e}")
        raise HTTPException(
            status_code=503, 
            detail="Service temporarily unavailable: Database connection failed. Please try again in a few moments."
        )

@app.get("/{secret_str}/config")
async def get_config(secret_str: str, user_data: UserData = Depends(get_user_data_dependency)):
    """
    Get the current configuration for a user (read-only, for UI purposes).

    Returns the user's configuration including M3U sources, schedule, and host URL.
    Note: Password is never returned for security reasons. Use a boolean
    to indicate if a password is set.
    """
    return {
        "m3u_sources": user_data.m3u_sources,
        "parser_schedule_crontab": user_data.parser_schedule_crontab,
        "host_url": str(user_data.host_url),
        "has_password": user_data.addon_password is not None  # Never return actual password
    }

@app.put("/{secret_str}/configure")
@app.patch("/{secret_str}/configure")
async def update_configure_addon(
    secret_str: str,
    request: UpdateConfigureRequest,
    user_data: UserData = Depends(get_user_data_dependency)
):
    """
    Update an existing user configuration. Only provided fields will be updated.
    
    Allows partial updates - only fields provided in the request will be changed.
    Empty string for addon_password removes the password.
    """
    try:
        logger.info(f"Update configuration requested for secret_str: {secret_str[:8]}...")

        # Merge update request with existing user data
        # Only update fields that are provided (not None)
        # For addon_password, empty string means remove password (set to None)
        updated_m3u_sources = request.m3u_sources if request.m3u_sources is not None else user_data.m3u_sources
        updated_crontab = request.parser_schedule_crontab if request.parser_schedule_crontab is not None else user_data.parser_schedule_crontab
        updated_host_url = request.host_url if request.host_url is not None else user_data.host_url
        if request.addon_password is not None:
            # Empty string means remove password, otherwise hash the provided value
            if request.addon_password == "":
                updated_password = None
            else:
                updated_password = hash_password(request.addon_password)
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
        
        # Invalidate manifest cache when configuration changes
        redis_store.redis_client.delete(f"manifest:{secret_str}")

        logger.info(f"Configuration updated for secret_str: {secret_str[:8]}...")
        logger.info(f"Triggering immediate M3U fetch for secret_str: {secret_str[:8]}...")
        scheduler.trigger_m3u_fetch_for_user(secret_str, updated_user_data)

        # Reload scheduler to update the scheduled job with new cron expression if it changed
        logger.info(f"Reloading scheduler to update configuration for secret_str: {secret_str[:8]}...")
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
        raise HTTPException(
            status_code=503, 
            detail="Service temporarily unavailable: Database connection failed. Please try again in a few moments."
        )

@app.get("/{secret_str}/manifest.json")
async def get_manifest(secret_str: str, user_data: UserData = Depends(get_user_data_dependency)):
    """
    Get the Stremio manifest for a user's addon configuration.
    
    Returns the manifest with available catalogs, genres, and resources.
    The manifest is cached and automatically invalidated when channels are updated.
    """
    logger.info(f"Manifest endpoint accessed for secret_str: {secret_str[:8]}...")

    # Check cache first (cache key includes secret_str for per-user caching)
    cache_key = f"manifest:{secret_str}"
    cached_manifest = redis_store.get(cache_key)
    if cached_manifest:
        try:
            return json.loads(cached_manifest)
        except json.JSONDecodeError:
            # If cached data is corrupted, regenerate
            logger.warning(f"Cached manifest for {secret_str[:8]}... is corrupted, regenerating")

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
            logger.error(f"Error decoding channel JSON from Redis: {e} - {channel_json[:100]}...")
            continue  # Skip invalid channels

    manifest = {
        "id": ADDON_ID,
        "version": ADDON_VERSION,
        "name": ADDON_NAME,
        "description": ADDON_DESCRIPTION,
        "logo": f"{HOST_URL}/static/logo.png",
        "behaviorHints": {
            "configurable": True,
            "configurationRequired": False
        },
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
    
    # Cache the manifest for 5 minutes (channels can change, so don't cache too long)
    redis_store.set(cache_key, json.dumps(manifest).encode(), expiration_time=300)
    
    return manifest

app.mount("/frontend", StaticFiles(directory="frontend", html=True), name="frontend")

@app.get("/{secret_str}/poster/{tvg_id}.png")
async def get_poster_image(secret_str: str, tvg_id: str, user_data: UserData = Depends(get_user_data_dependency)):
    """Get a poster image for a channel."""
    return await get_image_response(secret_str, tvg_id, get_poster)

@app.get("/{secret_str}/background/{tvg_id}.png")
async def get_background_image(secret_str: str, tvg_id: str, user_data: UserData = Depends(get_user_data_dependency)):
    """Get a background image for a channel."""
    return await get_image_response(secret_str, tvg_id, get_background)

@app.get("/{secret_str}/logo/{tvg_id}.png")
async def get_logo_image(secret_str: str, tvg_id: str, user_data: UserData = Depends(get_user_data_dependency)):
    """Get a logo image for a channel."""
    return await get_image_response(secret_str, tvg_id, get_logo)

@app.get("/{secret_str}/icon/{tvg_id}.png")
async def get_icon_image(secret_str: str, tvg_id: str, user_data: UserData = Depends(get_user_data_dependency)):
    """Get an icon image for a channel or the addon logo."""
    # For the manifest icon, we use a static logo. For channel icons, we use the channel's logo.
    if tvg_id == "logo":
        image_url = f"{HOST_URL}/icon/logo.png"
        channel_name = ADDON_NAME
        processed_image_bytes = await get_icon(redis_store, tvg_id, image_url, channel_name)
    else:
        channel = get_channel_data(secret_str, tvg_id)
        image_url = channel["tvg_logo"]
        # Use parsed event_title if available (for events), otherwise use tvg_name
        if channel.get("is_event") and channel.get("event_title"):
            channel_name = channel["event_title"]
            # For icons, use just the first line (before newline) to keep it shorter
            if "\n" in channel_name:
                channel_name = channel_name.split("\n")[0]
        else:
            channel_name = channel["tvg_name"]
        processed_image_bytes = await get_icon(redis_store, tvg_id, image_url, channel_name)

    if not processed_image_bytes.getvalue():
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to generate icon image. This may be a temporary issue - please try again later."
        )
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
            # Return a dummy item indicating no channels/events available
            empty_meta = create_empty_meta(type, secret_str, ADDON_ID_PREFIX, HOST_URL)
            return {"metas": [empty_meta]}

        filtered_channels = filter_channels(channels_data, type, extra_name, extra_value)

        if not filtered_channels:
            # Return a dummy item indicating no filtered results
            empty_meta = create_empty_meta(type, secret_str, ADDON_ID_PREFIX, HOST_URL)
            return {"metas": [empty_meta]}

        metas = [create_meta(channel, secret_str, ADDON_ID_PREFIX, HOST_URL) for channel in filtered_channels]

        return {"metas": metas}

    raise HTTPException(
        status_code=404, 
        detail=f"Catalog not found. Please check that you're using the correct catalog type and ID from your manifest."
    )

@app.get("/{secret_str}/meta/{type}/{id}.json")
async def get_meta(secret_str: str, type: str, id: str, user_data: UserData = Depends(get_user_data_dependency)):
    # Handle empty placeholder items
    if id in (f"{ADDON_ID_PREFIX}_empty_channels", f"{ADDON_ID_PREFIX}_empty_events"):
        # Return a simple meta for the empty placeholder
        empty_meta = create_empty_meta(type, secret_str, ADDON_ID_PREFIX, HOST_URL)
        empty_meta.update({"runtime": "", "releaseInfo": "", "links": []})
        return {"meta": empty_meta}
    
    if type == "events" and id.startswith(f"{ADDON_ID_PREFIX}_event_"):
        parts = id.split('_')
        tvg_id = parts[2]
        event_hash_suffix = parts[3]

        channel_json = redis_store.get_channel(secret_str, tvg_id)
        if channel_json:
            try:
                channel = json.loads(channel_json)
                if channel.get("is_event"):
                    current_event_hash_suffix = hashlib.sha256(channel["event_title"].encode()).hexdigest()[:EVENT_HASH_SUFFIX_LENGTH]
                    if current_event_hash_suffix == event_hash_suffix:
                        meta = create_meta(channel, secret_str, ADDON_ID_PREFIX, HOST_URL)
                        meta.update({"runtime": "", "releaseInfo": "", "links": []})
                        return {"meta": meta}
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse channel JSON for tvg_id {tvg_id} in get_meta: {e}")
                raise HTTPException(status_code=500, detail=f"Invalid channel data for tvg_id: {tvg_id}")
    elif type == "tv" and id.startswith(ADDON_ID_PREFIX):
        tvg_id = id.replace(ADDON_ID_PREFIX, "")
        channel_json = redis_store.get_channel(secret_str, tvg_id)
        if channel_json:
            try:
                channel = json.loads(channel_json)
                if not channel.get("is_event"):
                    meta = create_meta(channel, secret_str, ADDON_ID_PREFIX, HOST_URL)
                    
                    # Enhance with EPG program information if available
                    programs = redis_store.get_channel_programs(secret_str, tvg_id)
                    if programs:
                        now = datetime.now(pytz.UTC)
                        current_program = None
                        upcoming_programs = []
                        
                        for program in programs:
                            # Parse ISO format datetime strings back to datetime objects
                            try:
                                start_str = program["start"]
                                stop_str = program.get("stop")
                                
                                if isinstance(start_str, str):
                                    start = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
                                else:
                                    start = start_str
                                
                                if stop_str and isinstance(stop_str, str):
                                    stop = datetime.fromisoformat(stop_str.replace('Z', '+00:00'))
                                elif stop_str:
                                    stop = stop_str
                                else:
                                    stop = None
                                
                                # Ensure timezone-aware
                                if start.tzinfo is None:
                                    start = pytz.UTC.localize(start)
                                if stop and stop.tzinfo is None:
                                    stop = pytz.UTC.localize(stop)
                                
                                # Find current program
                                if start <= now and (not stop or stop >= now):
                                    current_program = program
                                    current_program["_start_dt"] = start
                                    current_program["_stop_dt"] = stop
                                # Find upcoming programs (next 3)
                                elif start > now and len(upcoming_programs) < 3:
                                    program["_start_dt"] = start
                                    program["_stop_dt"] = stop
                                    upcoming_programs.append(program)
                            except (ValueError, KeyError) as e:
                                logger.debug(f"Error parsing EPG program datetime: {e}")
                                continue
                        
                        # Build description with EPG info
                        description_parts = [meta["description"]]
                        
                        if current_program:
                            start_dt = current_program.get("_start_dt")
                            if start_dt:
                                start_time = start_dt.strftime("%I:%M %p")
                            else:
                                start_time = ""
                            desc_text = current_program.get("desc", "")
                            if desc_text:
                                description_parts.append(f"\n\nNow: {current_program['title']} ({start_time})")
                                description_parts.append(f"{desc_text}")
                            else:
                                description_parts.append(f"\n\nNow: {current_program['title']} ({start_time})")
                        
                        if upcoming_programs:
                            description_parts.append("\n\nUpcoming:")
                            for prog in upcoming_programs:
                                start_dt = prog.get("_start_dt")
                                if start_dt:
                                    start_time = start_dt.strftime("%I:%M %p")
                                else:
                                    start_time = ""
                                description_parts.append(f"• {prog['title']} ({start_time})")
                        
                        meta["description"] = "\n".join(description_parts)
                        
                        # Set releaseInfo to current program if available
                        if current_program:
                            meta["releaseInfo"] = f"Now: {current_program['title']}"
                        elif upcoming_programs:
                            next_start_dt = upcoming_programs[0].get("_start_dt")
                            if next_start_dt:
                                next_start = next_start_dt.strftime("%I:%M %p")
                            else:
                                next_start = ""
                            meta["releaseInfo"] = f"Next: {upcoming_programs[0]['title']} at {next_start}"
                    else:
                        meta.update({"runtime": "", "releaseInfo": "", "links": []})
                    
                    return {"meta": meta}
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse channel JSON for tvg_id {tvg_id} in get_meta: {e}")
                raise HTTPException(status_code=500, detail=f"Invalid channel data for tvg_id: {tvg_id}")
    raise HTTPException(
        status_code=404, 
        detail=f"Content not found. The item may have been removed or expired. Try refreshing your catalog."
    )

@app.get("/{secret_str}/stream/{type}/{id}.json")
async def get_stream(secret_str: str, type: str, id: str, user_data: UserData = Depends(get_user_data_dependency)):
    logger.info(f"Stream endpoint accessed for secret_str: {secret_str[:8]}..., type: {type}, id: {id}")

    if (type == "tv" or type == "events") and (id.startswith(f"{ADDON_ID_PREFIX}_event_") or id.startswith(ADDON_ID_PREFIX)):
        # Handle empty placeholder items
        if id in (f"{ADDON_ID_PREFIX}_empty_channels", f"{ADDON_ID_PREFIX}_empty_events"):
            raise HTTPException(status_code=404, detail="This is a placeholder item indicating no content is available. There are no streams to play.")
        
        if id.startswith(f"{ADDON_ID_PREFIX}_event_"):
            parts = id.split('_')
            tvg_id = parts[2]
        else:
            tvg_id = id.replace(ADDON_ID_PREFIX, "")
        
        # Handle empty_placeholder tvg_id
        if tvg_id == "empty_placeholder":
            raise HTTPException(status_code=404, detail="This is a placeholder item indicating no content is available. There are no streams to play.")
        
        channel_json = redis_store.get_channel(secret_str, tvg_id)
        if channel_json:
            try:
                channel = json.loads(channel_json)
                name = channel["event_title"] if channel.get("is_event") else channel["tvg_name"]
                stream = {
                    "name": name,
                    "description": f"Live stream for {name}",
                    "url": channel["stream_url"]
                }
                return {"streams": [stream]}
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse channel JSON for tvg_id {tvg_id} in get_stream: {e}")
                raise HTTPException(status_code=500, detail=f"Invalid channel data for tvg_id: {tvg_id}")
    raise HTTPException(
        status_code=404, 
        detail=f"Stream not found. The stream may have expired or the channel may no longer be available. Try refreshing your catalog."
    )
