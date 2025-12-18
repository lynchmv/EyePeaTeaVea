"""
Image processing utilities for generating and processing channel images.

This module handles:
- Placeholder image generation
- Image fetching and caching
- Image resizing and formatting for different use cases (poster, background, logo, icon)
- Local repository support for tv-logos to avoid rate limiting
"""
import os
import httpx
import asyncio
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError
import logging
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv
from .redis_store import RedisStore

load_dotenv()

logger = logging.getLogger(__name__)

# Local tv-logos repository path (optional, set via TV_LOGOS_REPO_PATH env var)
TV_LOGOS_REPO_PATH = os.getenv("TV_LOGOS_REPO_PATH", "").strip()
if TV_LOGOS_REPO_PATH:
    TV_LOGOS_REPO_PATH = os.path.abspath(TV_LOGOS_REPO_PATH)
    if not os.path.isdir(TV_LOGOS_REPO_PATH):
        logger.warning(f"TV_LOGOS_REPO_PATH '{TV_LOGOS_REPO_PATH}' is not a valid directory. Local repo disabled.")
        TV_LOGOS_REPO_PATH = ""
    else:
        logger.info(f"Local tv-logos repository enabled at: {TV_LOGOS_REPO_PATH}")
else:
    logger.info("Local tv-logos repository disabled (TV_LOGOS_REPO_PATH not set)")

# Image dimension constants
POSTER_WIDTH = 500
POSTER_HEIGHT = 750
BACKGROUND_WIDTH = 1024
BACKGROUND_HEIGHT = 576
LOGO_WIDTH = 500
LOGO_HEIGHT = 500
ICON_WIDTH = 256
ICON_HEIGHT = 256

# Placeholder image constants
DEFAULT_PLACEHOLDER_WIDTH = 500
DEFAULT_PLACEHOLDER_HEIGHT = 750

# Define the generic placeholder URL
GENERIC_PLACEHOLDER_URL = "https://via.placeholder.com/240x135.png?text=No+Logo"

# Cache constants
IMAGE_CACHE_EXPIRATION_SECONDS = 60 * 60 * 24 * 7  # 7 days
IMAGE_FETCH_TIMEOUT_SECONDS = 10

# Retry constants for rate limiting
MAX_RETRIES = 3
INITIAL_RETRY_DELAY = 1.0  # seconds
RETRY_BACKOFF_MULTIPLIER = 2.0  # exponential backoff multiplier

# GitHub tv-logos repository URL pattern
GITHUB_TV_LOGOS_BASE = "https://github.com/tv-logo/tv-logos/blob/main/"

def github_url_to_local_path(url: str) -> str | None:
    """
    Convert a GitHub tv-logos URL to a local file path.
    
    Converts URLs like:
    https://github.com/tv-logo/tv-logos/blob/main/countries/united-states/c-span-1-us.png?raw=true
    To local paths like:
    {TV_LOGOS_REPO_PATH}/countries/united-states/c-span-1-us.png
    
    Args:
        url: GitHub URL to convert
        
    Returns:
        Local file path if URL matches GitHub tv-logos pattern and repo is configured, None otherwise
    """
    if not TV_LOGOS_REPO_PATH:
        return None
    
    if not url.startswith(GITHUB_TV_LOGOS_BASE):
        return None
    
    try:
        # Parse URL to extract path
        parsed = urlparse(url)
        # Remove query parameters (?raw=true)
        path = parsed.path
        
        # Extract the file path after /blob/main/
        if "/blob/main/" in path:
            file_path = path.split("/blob/main/", 1)[1]
            local_path = os.path.join(TV_LOGOS_REPO_PATH, file_path)
            
            # Normalize path to prevent directory traversal
            local_path = os.path.normpath(local_path)
            
            # Ensure the path is within the repo directory (security check)
            if not local_path.startswith(os.path.normpath(TV_LOGOS_REPO_PATH)):
                logger.warning(f"Invalid path detected (directory traversal attempt): {url}")
                return None
            
            return local_path
    except Exception as e:
        logger.debug(f"Error converting GitHub URL to local path: {url} - {e}")
        return None
    
    return None

def read_local_image(file_path: str) -> bytes | None:
    """
    Read an image file from the local filesystem.
    
    Args:
        file_path: Path to the image file
        
    Returns:
        Image content as bytes if file exists and is readable, None otherwise
    """
    try:
        if os.path.exists(file_path) and os.path.isfile(file_path):
            with open(file_path, 'rb') as f:
                return f.read()
    except Exception as e:
        logger.debug(f"Error reading local image file {file_path}: {e}")
    
    return None

def generate_placeholder_image(
    title: str = "No Logo", 
    width: int = DEFAULT_PLACEHOLDER_WIDTH, 
    height: int = DEFAULT_PLACEHOLDER_HEIGHT, 
    monochrome: bool = False
) -> BytesIO:
    """
    Generate a placeholder image with centered text.
    
    Creates a black image with white text centered on it. Tries to use
    system fonts, falling back to default if none are available.
    
    Args:
        title: Text to display on the placeholder image
        width: Image width in pixels (default: DEFAULT_PLACEHOLDER_WIDTH)
        height: Image height in pixels (default: DEFAULT_PLACEHOLDER_HEIGHT)
        monochrome: If True, creates a grayscale image (default: False)
        
    Returns:
        BytesIO object containing the generated image (PNG for monochrome, JPEG otherwise)
        
    Examples:
        >>> img = generate_placeholder_image("CNN", POSTER_WIDTH, POSTER_HEIGHT)
        >>> isinstance(img, BytesIO)
        True
    """
    if monochrome:
        img = Image.new('L', (width, height), color = 0) # Black background, grayscale
        text_color = 255 # White text
    else:
        img = Image.new('RGB', (width, height), color = (0, 0, 0)) # Black background
        text_color = (255, 255, 255) # White text
        
    d = ImageDraw.Draw(img)
    
    # Try to load a custom font, fall back to default if not available
    font = ImageFont.load_default()
    font_paths = [
        "resources/fonts/IBMPlexSans-Medium.ttf",  # Project-specific font
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Common Linux font
        "/System/Library/Fonts/Helvetica.ttc",  # macOS font
        "C:/Windows/Fonts/arial.ttf",  # Windows font
    ]
    
    for font_path in font_paths:
        try:
            if os.path.exists(font_path):
                font = ImageFont.truetype(font_path, 40)
                logger.debug(f"Using font: {font_path}")
                break
        except Exception as e:
            logger.debug(f"Could not load font {font_path}: {e}")
            continue
    
    if font == ImageFont.load_default():
        logger.debug("Using default font (no custom font found)")

    text = title
    bbox = d.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    x = (width - text_width) / 2
    y = (height - text_height) / 2

    d.text((x, y), text, fill=text_color, font=font)
    
    byte_io = BytesIO()
    img.save(byte_io, "PNG" if monochrome else "JPEG", quality=85)
    byte_io.seek(0)
    return byte_io

async def fetch_image_content(redis_store: RedisStore, url: str) -> bytes:
    """
    Fetch image content from URL with caching support and retry logic.
    
    Checks in this order:
    1. Redis cache
    2. Local tv-logos repository (if enabled and URL matches)
    3. HTTP fetch with retry logic
    
    Implements retry logic with exponential backoff for rate limiting (429 errors).
    Caches successful fetches for future use.
    
    Args:
        redis_store: RedisStore instance for caching
        url: URL of the image to fetch
        
    Returns:
        Image content as bytes, or empty bytes if fetch fails after retries
        
    Examples:
        >>> content = await fetch_image_content(redis_store, "http://example.com/logo.png")
        >>> len(content) > 0
        True
    """
    cache_key = f"image_cache:{url}"
    cached_content = redis_store.get(cache_key)
    if cached_content:
        logger.debug(f"Returning cached image content for {url}")
        return cached_content
    
    # Try local repository first (for GitHub tv-logos URLs)
    local_path = github_url_to_local_path(url)
    if local_path:
        local_content = read_local_image(local_path)
        if local_content:
            logger.debug(f"Using local image from repository: {local_path}")
            # Cache the local content for future use
            redis_store.set(cache_key, local_content, expiration_time=IMAGE_CACHE_EXPIRATION_SECONDS)
            return local_content
        else:
            logger.debug(f"Local image not found at {local_path}, falling back to HTTP fetch")

    # Retry logic with exponential backoff for rate limiting
    retry_delay = INITIAL_RETRY_DELAY
    last_exception = None
    
    for attempt in range(MAX_RETRIES):
        try:
            async with httpx.AsyncClient() as client:
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"}
                response = await client.get(url, headers=headers, timeout=IMAGE_FETCH_TIMEOUT_SECONDS, follow_redirects=True)
                
                # Handle rate limiting (429) with retry
                if response.status_code == 429:
                    if attempt < MAX_RETRIES - 1:
                        # Check for Retry-After header
                        retry_after = response.headers.get("Retry-After")
                        if retry_after:
                            try:
                                wait_time = float(retry_after)
                            except ValueError:
                                wait_time = retry_delay
                        else:
                            wait_time = retry_delay
                        
                        logger.warning(
                            f"Rate limited (429) fetching image from {url}. "
                            f"Retrying in {wait_time:.1f}s (attempt {attempt + 1}/{MAX_RETRIES})"
                        )
                        await asyncio.sleep(wait_time)
                        retry_delay *= RETRY_BACKOFF_MULTIPLIER
                        continue
                    else:
                        logger.error(f"Rate limit exceeded after {MAX_RETRIES} attempts for {url}")
                        return b''
                
                response.raise_for_status()
                
                if not response.headers.get("Content-Type", "").lower().startswith("image/"):
                    raise ValueError(f"Unexpected content type: {response.headers.get('Content-Type', 'unknown')}")
                
                content = response.content
                # Cache the fetched content for future use
                redis_store.set(cache_key, content, expiration_time=IMAGE_CACHE_EXPIRATION_SECONDS)
                return content
                
        except httpx.HTTPStatusError as e:
            # For non-429 errors, don't retry
            if e.response.status_code != 429:
                logger.warning(f"HTTP status error fetching image from {url}: {e}")
                return b''
            # 429 errors should be caught above, but handle here as fallback
            last_exception = e
            if attempt < MAX_RETRIES - 1:
                logger.warning(
                    f"HTTP status error (429) fetching image from {url}. "
                    f"Retrying in {retry_delay:.1f}s (attempt {attempt + 1}/{MAX_RETRIES})"
                )
                await asyncio.sleep(retry_delay)
                retry_delay *= RETRY_BACKOFF_MULTIPLIER
                continue
            else:
                logger.error(f"Rate limit exceeded after {MAX_RETRIES} attempts for {url}")
                return b''
                
        except httpx.RequestError as e:
            # Network errors - retry with backoff
            last_exception = e
            if attempt < MAX_RETRIES - 1:
                logger.warning(
                    f"Request error fetching image from {url}: {e}. "
                    f"Retrying in {retry_delay:.1f}s (attempt {attempt + 1}/{MAX_RETRIES})"
                )
                await asyncio.sleep(retry_delay)
                retry_delay *= RETRY_BACKOFF_MULTIPLIER
                continue
            else:
                logger.error(f"Failed to fetch image from {url} after {MAX_RETRIES} attempts: {e}")
                return b''
                
        except ValueError as e:
            # Content type errors - don't retry
            logger.warning(f"Error fetching image from {url}: {e}")
            return b''
    
    # Should not reach here, but handle it gracefully
    if last_exception:
        logger.error(f"Failed to fetch image from {url} after {MAX_RETRIES} attempts: {last_exception}")
    return b''

async def process_image(
    redis_store: RedisStore, 
    tvg_id: str, 
    image_url: str, 
    title: str, 
    width: int, 
    height: int, 
    image_type: str, 
    monochrome: bool = False
) -> BytesIO:
    """
    Process and resize an image for a specific use case.
    
    Processes images by:
    1. Checking cache (shared across users for same channel/image_type)
    2. Generating placeholder if URL is generic placeholder
    3. Fetching image content
    4. Resizing while maintaining aspect ratio
    5. Centering on black background
    6. Caching the result
    
    Args:
        redis_store: RedisStore instance for caching
        tvg_id: Channel identifier
        image_url: URL of the image to process
        title: Title for placeholder generation if fetch fails
        width: Target width in pixels
        height: Target height in pixels
        image_type: Type of image ("poster", "background", "logo", "icon")
        monochrome: If True, converts to grayscale (default: False)
        
    Returns:
        BytesIO object containing the processed image
        
    Examples:
        >>> img = await process_image(redis_store, "CNN", "http://...", "CNN", POSTER_WIDTH, POSTER_HEIGHT, "poster")
        >>> isinstance(img, BytesIO)
        True
    """
    # Cache key is based on tvg_id and image_type, not user-specific
    # This allows sharing processed images across users since the same channel logo produces the same processed image
    cache_key = f"{tvg_id}_{image_type}"
    cached_image = redis_store.get_processed_image(cache_key)
    if cached_image:
        logger.info(f"Returning cached image for {cache_key}")
        return BytesIO(cached_image)

    if image_url == GENERIC_PLACEHOLDER_URL:
        processed_image = generate_placeholder_image(title, width, height, monochrome)
        redis_store.store_processed_image(cache_key, processed_image.getvalue())
        return processed_image

    content = await fetch_image_content(redis_store, image_url)
    if not content:
        return generate_placeholder_image(title, width, height, monochrome)

    try:
        original_image = Image.open(BytesIO(content))
        if monochrome:
            original_image = original_image.convert("L")
        else:
            original_image = original_image.convert("RGB")

        original_width, original_height = original_image.size

        ratio = min(width / original_width, height / original_height)
        new_width = int(original_width * ratio)
        new_height = int(original_height * ratio)

        resized_image = original_image.resize((new_width, new_height), Image.Resampling.LANCZOS)

        if monochrome:
            background = Image.new('L', (width, height), 0)
        else:
            background = Image.new('RGB', (width, height), (0, 0, 0))

        paste_x = (width - new_width) // 2
        paste_y = (height - new_height) // 2

        background.paste(resized_image, (paste_x, paste_y))

        byte_io = BytesIO()
        background.save(byte_io, "PNG" if monochrome else "JPEG", quality=85)
        byte_io.seek(0)
        redis_store.store_processed_image(cache_key, byte_io.getvalue())
        return byte_io
    except UnidentifiedImageError:
        processed_image = generate_placeholder_image(title, width, height, monochrome)
        redis_store.store_processed_image(cache_key, processed_image.getvalue())
        return processed_image
    except Exception as e:
        logger.error(f"Error processing image for URL: {image_url} - {e}")
        processed_image = generate_placeholder_image(title, width, height, monochrome)
        redis_store.store_processed_image(cache_key, processed_image.getvalue())
        return processed_image

async def get_poster(redis_store: RedisStore, tvg_id: str, image_url: str, title: str) -> BytesIO:
    """
    Get a poster image (portrait format).
    
    Args:
        redis_store: RedisStore instance for caching
        tvg_id: Channel identifier
        image_url: URL of the image
        title: Title for placeholder if needed
        
    Returns:
        BytesIO object containing the poster image
    """
    return await process_image(redis_store, tvg_id, image_url, title, POSTER_WIDTH, POSTER_HEIGHT, "poster")

async def get_background(redis_store: RedisStore, tvg_id: str, image_url: str, title: str) -> BytesIO:
    """
    Get a background image (widescreen format).
    
    Args:
        redis_store: RedisStore instance for caching
        tvg_id: Channel identifier
        image_url: URL of the image
        title: Title for placeholder if needed
        
    Returns:
        BytesIO object containing the background image
    """
    return await process_image(redis_store, tvg_id, image_url, title, BACKGROUND_WIDTH, BACKGROUND_HEIGHT, "background")

async def get_logo(redis_store: RedisStore, tvg_id: str, image_url: str, title: str) -> BytesIO:
    """
    Get a logo image (square format).
    
    Args:
        redis_store: RedisStore instance for caching
        tvg_id: Channel identifier
        image_url: URL of the image
        title: Title for placeholder if needed
        
    Returns:
        BytesIO object containing the logo image
    """
    return await process_image(redis_store, tvg_id, image_url, title, LOGO_WIDTH, LOGO_HEIGHT, "logo")

async def get_icon(redis_store: RedisStore, tvg_id: str, image_url: str, title: str) -> BytesIO:
    """
    Get an icon image (square format, monochrome).
    
    Args:
        redis_store: RedisStore instance for caching
        tvg_id: Channel identifier
        image_url: URL of the image
        title: Title for placeholder if needed
        
    Returns:
        BytesIO object containing the icon image (grayscale)
    """
    return await process_image(redis_store, tvg_id, image_url, title, ICON_WIDTH, ICON_HEIGHT, "icon", monochrome=True)
