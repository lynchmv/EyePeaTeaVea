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
    # Convert to absolute path
    original_path = TV_LOGOS_REPO_PATH
    TV_LOGOS_REPO_PATH = os.path.abspath(TV_LOGOS_REPO_PATH)
    
    # Check if directory exists
    if not os.path.exists(TV_LOGOS_REPO_PATH):
        logger.warning(f"TV_LOGOS_REPO_PATH '{TV_LOGOS_REPO_PATH}' (from '{original_path}') does not exist. Local repo disabled.")
        TV_LOGOS_REPO_PATH = ""
    elif not os.path.isdir(TV_LOGOS_REPO_PATH):
        logger.warning(f"TV_LOGOS_REPO_PATH '{TV_LOGOS_REPO_PATH}' exists but is not a directory. Local repo disabled.")
        TV_LOGOS_REPO_PATH = ""
    else:
        # Verify it's actually the tv-logos repo by checking for a known file
        test_file = os.path.join(TV_LOGOS_REPO_PATH, "countries")
        if os.path.exists(test_file):
            logger.info(f"✓ Local tv-logos repository enabled at: {TV_LOGOS_REPO_PATH}")
        else:
            logger.warning(f"TV_LOGOS_REPO_PATH '{TV_LOGOS_REPO_PATH}' exists but doesn't appear to be tv-logos repo (missing 'countries' directory). Local repo disabled.")
            TV_LOGOS_REPO_PATH = ""
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
PLACEHOLDER_CACHE_VERSION = "v2"  # Increment this when placeholder generation changes to invalidate old cached placeholders

# Retry constants for rate limiting
MAX_RETRIES = 3
INITIAL_RETRY_DELAY = 1.0  # seconds
RETRY_BACKOFF_MULTIPLIER = 2.0  # exponential backoff multiplier

# Shared HTTP client for image fetching (reused across requests for better performance)
_http_client: httpx.AsyncClient | None = None

def get_http_client() -> httpx.AsyncClient:
    """
    Get or create the shared HTTP client instance.
    
    Creates a singleton HTTP client with connection pooling for better performance.
    The client is reused across all image fetch requests.
    
    Returns:
        Shared httpx.AsyncClient instance
    """
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            timeout=IMAGE_FETCH_TIMEOUT_SECONDS,
            follow_redirects=True,
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"}
        )
    return _http_client

async def close_http_client() -> None:
    """
    Close the shared HTTP client.
    
    Should be called during application shutdown to properly clean up connections.
    """
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None

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
        logger.debug(f"TV_LOGOS_REPO_PATH not set, cannot use local repository for: {url}")
        return None
    
    if not url.startswith(GITHUB_TV_LOGOS_BASE):
        logger.debug(f"URL doesn't match GitHub tv-logos pattern: {url}")
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
            repo_path_norm = os.path.normpath(TV_LOGOS_REPO_PATH)
            local_path_norm = os.path.normpath(local_path)
            if not local_path_norm.startswith(repo_path_norm + os.sep) and local_path_norm != repo_path_norm:
                logger.warning(f"Invalid path detected (directory traversal attempt): {url} -> {local_path_norm} (repo: {repo_path_norm})")
                return None
            
            logger.debug(f"Converted GitHub URL to local path: {url} -> {local_path}")
            return local_path
        else:
            logger.debug(f"URL doesn't contain /blob/main/ path: {url}")
            return None
    except Exception as e:
        logger.warning(f"Error converting GitHub URL to local path: {url} - {e}")
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
        if os.path.exists(file_path):
            if os.path.isfile(file_path):
                with open(file_path, 'rb') as f:
                    content = f.read()
                    logger.debug(f"Successfully read local image: {file_path} ({len(content)} bytes)")
                    return content
            else:
                logger.debug(f"Path exists but is not a file: {file_path}")
        else:
            logger.debug(f"Local image file does not exist: {file_path}")
    except Exception as e:
        logger.warning(f"Error reading local image file {file_path}: {e}")
    
    return None

def generate_placeholder_image(
    title: str = "No Logo", 
    width: int = DEFAULT_PLACEHOLDER_WIDTH, 
    height: int = DEFAULT_PLACEHOLDER_HEIGHT, 
    monochrome: bool = False
) -> BytesIO:
    """
    Generate a placeholder image with centered, legible text.
    
    Creates a dark gray image with white text that has a shadow for better readability.
    Font size scales with image dimensions, and long text is wrapped automatically.
    
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
    # Use dark gray background instead of pure black for better contrast
    if monochrome:
        img = Image.new('L', (width, height), color=30)  # Dark gray background
        text_color = 255  # White text
        shadow_color = 0  # Black shadow
    else:
        img = Image.new('RGB', (width, height), color=(30, 30, 30))  # Dark gray background
        text_color = (255, 255, 255)  # White text
        shadow_color = (0, 0, 0)  # Black shadow
    
    d = ImageDraw.Draw(img)
    
    # Calculate font size based on image dimensions - use a MUCH larger percentage for maximum visibility
    # Use 35-40% of the smaller dimension - this should make text VERY visible
    smaller_dimension = min(width, height)
    # Calculate font size: aim for 35-40% of smaller dimension for maximum visibility
    # For 500x500 logo: 500 * 0.38 = 190px font (very large!)
    base_font_size = max(100, min(400, int(smaller_dimension * 0.38)))  # 38% of smaller dimension
    
    logger.info(f"Generating placeholder image: {width}x{height}, font size: {base_font_size}px, title: '{title[:50]}...'")
    
    # Try to load a custom scalable font - CRITICAL: default font doesn't scale!
    font = None
    font_loaded = False
    font_paths = [
        # Linux fonts (most likely in Docker)
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Bold for better readability
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Common Linux font
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",  # Another Linux option
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        # Project-specific font
        "resources/fonts/IBMPlexSans-Medium.ttf",
        # macOS fonts
        "/System/Library/Fonts/Helvetica.ttc",
        # Windows fonts
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    
    for font_path in font_paths:
        try:
            if os.path.exists(font_path):
                font = ImageFont.truetype(font_path, base_font_size)
                font_loaded = True
                logger.info(f"✓ Using scalable font: {font_path} at size {base_font_size}px for '{title[:30]}...'")
                break
            else:
                logger.debug(f"Font not found: {font_path}")
        except Exception as e:
            logger.warning(f"Could not load font {font_path}: {e}")
            continue
    
    # CRITICAL: If no scalable font found, use a workaround
    # ImageFont.load_default() is a bitmap font that doesn't scale!
    # Workaround: Render text on a larger temporary image, then scale it down
    scale_factor = 1.0
    if not font_loaded:
        logger.error(f"⚠️  NO SCALABLE FONTS FOUND! Fonts should be at:")
        logger.error(f"⚠️  /usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
        logger.error(f"⚠️  /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
        logger.error(f"⚠️  Using workaround: rendering at {base_font_size/10:.0f}x scale then scaling down")
        font = ImageFont.load_default()
        # Default font is ~10px, so scale up the rendering surface significantly
        scale_factor = max(3.0, base_font_size / 10.0)  # At least 3x scale, or more for larger fonts
        logger.warning(f"Scale factor: {scale_factor:.1f}x (default font is ~10px, target is {base_font_size}px)")
    
    # Prepare text - truncate very long names and wrap if needed
    text = title.strip()
    if not text:
        text = "No Logo"
    
    # Calculate available width (leave 10% padding on each side)
    max_text_width = width * 0.8
    padding = width * 0.1
    
    # Wrap text if it's too long
    lines = []
    words = text.split()
    current_line = []
    current_width = 0
    
    for word in words:
        # Test width of word with space
        test_text = " ".join(current_line + [word]) if current_line else word
        bbox = d.textbbox((0, 0), test_text, font=font)
        test_width = bbox[2] - bbox[0]
        
        if test_width <= max_text_width:
            current_line.append(word)
            current_width = test_width
        else:
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [word]
            # If single word is too long, truncate it
            bbox = d.textbbox((0, 0), word, font=font)
            word_width = bbox[2] - bbox[0]
            if word_width > max_text_width:
                # Truncate word with ellipsis
                truncated = word
                while truncated:
                    test_text = truncated + "..."
                    bbox = d.textbbox((0, 0), test_text, font=font)
                    if bbox[2] - bbox[0] <= max_text_width:
                        lines.append(test_text)
                        current_line = []
                        break
                    truncated = truncated[:-1]
                if not truncated:
                    lines.append(word[:20] + "...")  # Fallback truncation
            else:
                current_width = word_width
    
    if current_line:
        lines.append(" ".join(current_line))
    
    if not lines:
        lines = [text[:30] + "..." if len(text) > 30 else text]
    
    # If using default font (non-scalable), render on larger canvas then scale down
    if not font_loaded and scale_factor > 1.0:
        logger.warning(f"Rendering with scale factor {scale_factor:.1f}x due to non-scalable font")
        # Create a larger temporary image for rendering (scale up)
        temp_width = int(width * scale_factor)
        temp_height = int(height * scale_factor)
        if monochrome:
            temp_img = Image.new('L', (temp_width, temp_height), color=30)
        else:
            temp_img = Image.new('RGB', (temp_width, temp_height), color=(30, 30, 30))
        temp_d = ImageDraw.Draw(temp_img)
        
        # Use the same lines, but draw them larger by using the scaled dimensions
        # Default font is ~10px, so spacing should scale proportionally
        scaled_line_height = 15 * scale_factor  # ~15px line height scaled up
        scaled_total_height = len(lines) * scaled_line_height
        scaled_start_y = (temp_height - scaled_total_height) / 2
        scaled_max_width = temp_width * 0.8
        
        # Draw text on scaled image (text will appear larger when scaled down)
        for i, line in enumerate(lines):
            y_pos = scaled_start_y + (i * scaled_line_height)
            bbox = temp_d.textbbox((0, 0), line, font=font)
            text_width = bbox[2] - bbox[0]
            x_pos = (temp_width - text_width) / 2
            
            # Draw shadow (scaled)
            shadow_offset = max(2, int(3 * scale_factor))
            temp_d.text((x_pos + shadow_offset, y_pos + shadow_offset), line, fill=shadow_color, font=font)
            temp_d.text((x_pos, y_pos), line, fill=text_color, font=font)
        
        # Scale down to target size using high-quality resampling
        img = temp_img.resize((width, height), Image.Resampling.LANCZOS)
        d = ImageDraw.Draw(img)  # Recreate draw object for final image
        logger.info(f"Scaled image from {temp_width}x{temp_height} to {width}x{height}")
    else:
        # Normal rendering with scalable font
        # Calculate total text height
        if font_loaded:
            line_height = base_font_size * 1.3  # 30% spacing between lines for scalable fonts
        else:
            estimated_font_height = 12
            line_height = estimated_font_height * 1.5
        total_text_height = len(lines) * line_height
        
        # Center text vertically
        start_y = (height - total_text_height) / 2
        
        # Draw each line with shadow for better readability
        for i, line in enumerate(lines):
            y_pos = start_y + (i * line_height)
            
            # Measure text for centering
            bbox = d.textbbox((0, 0), line, font=font)
            text_width = bbox[2] - bbox[0]
            x_pos = (width - text_width) / 2
            
            # Draw shadow (offset by 2 pixels for depth)
            shadow_offset = max(1, int(base_font_size * 0.05))  # Scale shadow with font size
            d.text((x_pos + shadow_offset, y_pos + shadow_offset), line, fill=shadow_color, font=font)
            
            # Draw main text
            d.text((x_pos, y_pos), line, fill=text_color, font=font)
    
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
    if url.startswith("https://github.com/tv-logo/tv-logos"):
        logger.info(f"GitHub tv-logos URL detected: {url}")
        logger.info(f"  TV_LOGOS_REPO_PATH configured: {bool(TV_LOGOS_REPO_PATH)}")
        if TV_LOGOS_REPO_PATH:
            logger.info(f"  TV_LOGOS_REPO_PATH value: {TV_LOGOS_REPO_PATH}")
            logger.info(f"  TV_LOGOS_REPO_PATH exists: {os.path.exists(TV_LOGOS_REPO_PATH)}")
            logger.info(f"  TV_LOGOS_REPO_PATH isdir: {os.path.isdir(TV_LOGOS_REPO_PATH) if os.path.exists(TV_LOGOS_REPO_PATH) else 'N/A'}")
    
    local_path = github_url_to_local_path(url)
    if local_path:
        logger.info(f"Checking local repository for: {url}")
        logger.info(f"  Converted to local path: {local_path}")
        logger.info(f"  File exists: {os.path.exists(local_path)}")
        if os.path.exists(local_path):
            logger.info(f"  File is file: {os.path.isfile(local_path)}")
            logger.info(f"  File size: {os.path.getsize(local_path) if os.path.isfile(local_path) else 'N/A'} bytes")
        local_content = read_local_image(local_path)
        if local_content:
            logger.info(f"✓ Using local image from repository: {local_path} ({len(local_content)} bytes)")
            # Cache the local content for future use
            redis_store.set(cache_key, local_content, expiration_time=IMAGE_CACHE_EXPIRATION_SECONDS)
            return local_content
        else:
            logger.warning(f"✗ Local image not found or unreadable at {local_path}, falling back to HTTP fetch")
    else:
        if url.startswith("https://github.com/tv-logo/tv-logos"):
            logger.warning(f"✗ GitHub tv-logos URL detected but local repo check returned None")
            logger.warning(f"  TV_LOGOS_REPO_PATH: {TV_LOGOS_REPO_PATH}")
            logger.warning(f"  URL matches base pattern: {url.startswith(GITHUB_TV_LOGOS_BASE)}")

    # Retry logic with exponential backoff for rate limiting
    retry_delay = INITIAL_RETRY_DELAY
    last_exception = None
    
    # Get shared HTTP client for connection reuse
    client = get_http_client()
    
    for attempt in range(MAX_RETRIES):
        try:
            response = await client.get(url)
            
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
    # Include placeholder version for placeholder images to invalidate cache when generation changes
    is_placeholder = image_url == GENERIC_PLACEHOLDER_URL
    cache_key = f"{tvg_id}_{image_type}"
    if is_placeholder:
        cache_key = f"{cache_key}_placeholder_{PLACEHOLDER_CACHE_VERSION}"
    
    cached_image = redis_store.get_processed_image(cache_key)
    if cached_image:
        logger.info(f"Returning cached image for {cache_key}")
        return BytesIO(cached_image)

    if is_placeholder:
        processed_image = generate_placeholder_image(title, width, height, monochrome)
        redis_store.store_processed_image(cache_key, processed_image.getvalue())
        return processed_image

    content = await fetch_image_content(redis_store, image_url)
    if not content:
        # Generate placeholder when fetch fails - use versioned cache key
        placeholder_cache_key = f"{cache_key}_placeholder_{PLACEHOLDER_CACHE_VERSION}"
        cached_placeholder = redis_store.get_processed_image(placeholder_cache_key)
        if cached_placeholder:
            logger.info(f"Returning cached placeholder for {placeholder_cache_key}")
            return BytesIO(cached_placeholder)
        
        processed_image = generate_placeholder_image(title, width, height, monochrome)
        redis_store.store_processed_image(placeholder_cache_key, processed_image.getvalue())
        return processed_image

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
        # Generate placeholder when image can't be identified - use versioned cache key
        placeholder_cache_key = f"{cache_key}_placeholder_{PLACEHOLDER_CACHE_VERSION}"
        cached_placeholder = redis_store.get_processed_image(placeholder_cache_key)
        if cached_placeholder:
            return BytesIO(cached_placeholder)
        processed_image = generate_placeholder_image(title, width, height, monochrome)
        redis_store.store_processed_image(placeholder_cache_key, processed_image.getvalue())
        return processed_image
    except Exception as e:
        logger.error(f"Error processing image for URL: {image_url} - {e}")
        # Generate placeholder on error - use versioned cache key
        placeholder_cache_key = f"{cache_key}_placeholder_{PLACEHOLDER_CACHE_VERSION}"
        cached_placeholder = redis_store.get_processed_image(placeholder_cache_key)
        if cached_placeholder:
            return BytesIO(cached_placeholder)
        processed_image = generate_placeholder_image(title, width, height, monochrome)
        redis_store.store_processed_image(placeholder_cache_key, processed_image.getvalue())
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
