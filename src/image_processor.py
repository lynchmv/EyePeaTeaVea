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
import colorsys
import warnings
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
PLACEHOLDER_CACHE_VERSION = "v12"  # Increment this when placeholder generation changes to invalidate old cached placeholders

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

def _load_font(size: int) -> tuple[ImageFont.FreeTypeFont | ImageFont.ImageFont, bool]:
    """
    Load a scalable font at the given size.
    
    Returns:
        Tuple of (font, font_loaded) where font_loaded indicates if a scalable font was found
    """
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    
    for font_path in font_paths:
        try:
            if os.path.exists(font_path):
                return ImageFont.truetype(font_path, size), True
        except Exception:
            continue
    
    return ImageFont.load_default(), False

def _create_gradient_background(
    width: int, 
    height: int, 
    start_color: tuple[int, int, int], 
    end_color: tuple[int, int, int],
    direction: str = "vertical"
) -> Image.Image:
    """
    Create a gradient background image.
    
    Args:
        width: Image width
        height: Image height
        start_color: RGB tuple for start color
        end_color: RGB tuple for end color
        direction: "vertical", "horizontal", or "diagonal"
        
    Returns:
        PIL Image with gradient background
    """
    img = Image.new('RGB', (width, height))
    pixels = img.load()
    
    if direction == "vertical":
        for y in range(height):
            ratio = y / height
            r = int(start_color[0] * (1 - ratio) + end_color[0] * ratio)
            g = int(start_color[1] * (1 - ratio) + end_color[1] * ratio)
            b = int(start_color[2] * (1 - ratio) + end_color[2] * ratio)
            for x in range(width):
                pixels[x, y] = (r, g, b)
    elif direction == "horizontal":
        for x in range(width):
            ratio = x / width
            r = int(start_color[0] * (1 - ratio) + end_color[0] * ratio)
            g = int(start_color[1] * (1 - ratio) + end_color[1] * ratio)
            b = int(start_color[2] * (1 - ratio) + end_color[2] * ratio)
            for y in range(height):
                pixels[x, y] = (r, g, b)
    else:  # diagonal
        max_dist = (width * width + height * height) ** 0.5
        for y in range(height):
            for x in range(width):
                # Distance from top-left corner
                dist = ((x * x + y * y) ** 0.5) / max_dist
                ratio = min(1.0, dist)
                r = int(start_color[0] * (1 - ratio) + end_color[0] * ratio)
                g = int(start_color[1] * (1 - ratio) + end_color[1] * ratio)
                b = int(start_color[2] * (1 - ratio) + end_color[2] * ratio)
                pixels[x, y] = (r, g, b)
    
    return img

def _wrap_text(text: str, font: ImageFont.FreeTypeFont | ImageFont.ImageFont, max_width: int) -> list[str]:
    """
    Wrap text to fit within max_width.
    
    Returns:
        List of text lines
    """
    words = text.split()
    lines = []
    current_line = []
    
    for word in words:
        test_text = " ".join(current_line + [word]) if current_line else word
        # Use a temporary image to measure text
        temp_img = Image.new('RGB', (100, 100))
        temp_draw = ImageDraw.Draw(temp_img)
        bbox = temp_draw.textbbox((0, 0), test_text, font=font)
        text_width = bbox[2] - bbox[0]
        
        if text_width <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(" ".join(current_line))
            # Check if single word is too long
            bbox = temp_draw.textbbox((0, 0), word, font=font)
            if bbox[2] - bbox[0] > max_width:
                # Truncate long word
                truncated = word
                while truncated:
                    test = truncated + "..."
                    bbox = temp_draw.textbbox((0, 0), test, font=font)
                    if bbox[2] - bbox[0] <= max_width:
                        lines.append(test)
                        current_line = []
                        break
                    truncated = truncated[:-1]
                if truncated == "":
                    lines.append(word[:15] + "...")
                    current_line = []
            else:
                current_line = [word]
    
    if current_line:
        lines.append(" ".join(current_line))
    
    return lines if lines else [text[:30] + "..." if len(text) > 30 else text]

def generate_logo_placeholder(title: str, width: int = LOGO_WIDTH, height: int = LOGO_HEIGHT) -> BytesIO:
    """
    Generate a modern logo placeholder with gradient background and bold text.
    
    Creates a square logo with a vibrant gradient and centered text.
    """
    text = title.strip() or "LOGO"
    logger.info(f"Generating logo placeholder: {width}x{height} for '{text[:50]}...'")
    
    # Generate color based on title hash for consistency
    title_hash = hash(title) % 360
    hue = title_hash
    
    # Create vibrant gradient background
    # Use complementary colors for gradient
    color1_rgb = tuple(int(c * 255) for c in colorsys.hls_to_rgb(hue / 360, 0.3, 0.8))
    color2_rgb = tuple(int(c * 255) for c in colorsys.hls_to_rgb((hue + 60) / 360, 0.2, 0.9))
    
    img = _create_gradient_background(width, height, color1_rgb, color2_rgb, "diagonal")
    
    # Add subtle overlay for better text readability
    overlay = Image.new('RGBA', (width, height), (0, 0, 0, 60))
    img = Image.alpha_composite(img.convert('RGBA'), overlay).convert('RGB')
    
    d = ImageDraw.Draw(img)
    
    # Calculate font size (8% of smaller dimension)
    smaller_dim = min(width, height)
    font_size = max(20, min(80, int(smaller_dim * 0.08)))
    font, font_loaded = _load_font(font_size)
    
    # Wrap text
    max_text_width = int(width * 0.85)
    lines = _wrap_text(text, font, max_text_width)
    
    # Calculate text positioning
    if font_loaded:
        line_height = int(font_size * 1.2)
    else:
        line_height = int(font_size * 1.3)
    
    total_height = len(lines) * line_height
    start_y = (height - total_height) // 2
    
    # Draw text with shadow
    text_color = (255, 255, 255)
    shadow_color = (0, 0, 0)
    shadow_offset = max(2, font_size // 30)
    
    for i, line in enumerate(lines):
        y_pos = start_y + (i * line_height)
        # Measure text
        temp_img = Image.new('RGB', (100, 100))
        temp_draw = ImageDraw.Draw(temp_img)
        bbox = temp_draw.textbbox((0, 0), line, font=font)
        text_width = bbox[2] - bbox[0]
        x_pos = (width - text_width) // 2
        
        # Draw shadow
        d.text((x_pos + shadow_offset, y_pos + shadow_offset), line, fill=shadow_color, font=font)
        # Draw text
        d.text((x_pos, y_pos), line, fill=text_color, font=font)
    
    byte_io = BytesIO()
    img.save(byte_io, "PNG", quality=95)
    byte_io.seek(0)
    return byte_io

def generate_poster_placeholder(title: str, width: int = POSTER_WIDTH, height: int = POSTER_HEIGHT) -> BytesIO:
    """
    Generate a modern poster placeholder with cinematic gradient and elegant typography.
    
    Creates a portrait poster with a dark, cinematic gradient and centered text.
    """
    text = title.strip() or "POSTER"
    logger.info(f"Generating poster placeholder: {width}x{height} for '{text[:50]}...'")
    
    # Create cinematic dark gradient (dark blue to dark purple)
    start_color = (20, 25, 40)  # Dark blue-gray
    end_color = (30, 20, 35)     # Dark purple-gray
    
    img = _create_gradient_background(width, height, start_color, end_color, "vertical")
    
    # Add subtle vignette effect using gradient overlay
    overlay = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    overlay_pixels = overlay.load()
    center_x, center_y = width // 2, height // 2
    max_dist = ((width // 2) ** 2 + (height // 2) ** 2) ** 0.5
    
    for y in range(height):
        for x in range(width):
            dist = ((x - center_x) ** 2 + (y - center_y) ** 2) ** 0.5
            # Darker at edges
            alpha = int(40 * (dist / max_dist) ** 2)
            overlay_pixels[x, y] = (0, 0, 0, min(alpha, 80))
    
    img = Image.alpha_composite(img.convert('RGBA'), overlay).convert('RGB')
    
    d = ImageDraw.Draw(img)
    
    # Calculate font size (16% of width for posters)
    font_size = max(35, min(120, int(width * 0.16)))
    font, font_loaded = _load_font(font_size)
    
    # Wrap text
    max_text_width = int(width * 0.8)
    lines = _wrap_text(text, font, max_text_width)
    
    # Calculate text positioning
    if font_loaded:
        line_height = int(font_size * 1.4)
    else:
        line_height = int(font_size * 1.5)
    
    total_height = len(lines) * line_height
    start_y = (height - total_height) // 2
    
    # Draw text with glow effect
    text_color = (255, 255, 255)
    shadow_color = (0, 0, 0)
    shadow_offset = max(3, font_size // 25)
    
    for i, line in enumerate(lines):
        y_pos = start_y + (i * line_height)
        # Measure text
        temp_img = Image.new('RGB', (100, 100))
        temp_draw = ImageDraw.Draw(temp_img)
        bbox = temp_draw.textbbox((0, 0), line, font=font)
        text_width = bbox[2] - bbox[0]
        x_pos = (width - text_width) // 2
        
        # Draw multiple shadow layers for glow effect
        for offset in range(shadow_offset, 0, -1):
            alpha = 50 // (offset + 1)
            d.text((x_pos + offset, y_pos + offset), line, fill=shadow_color, font=font)
        # Draw main text
        d.text((x_pos, y_pos), line, fill=text_color, font=font)
    
    byte_io = BytesIO()
    img.save(byte_io, "JPEG", quality=90)
    byte_io.seek(0)
    return byte_io

def generate_background_placeholder(title: str, width: int = BACKGROUND_WIDTH, height: int = BACKGROUND_HEIGHT) -> BytesIO:
    """
    Generate a modern background placeholder with wide gradient and subtle text.
    
    Creates a widescreen background with a smooth gradient and centered, subtle text.
    """
    text = title.strip() or "BACKGROUND"
    logger.info(f"Generating background placeholder: {width}x{height} for '{text[:50]}...'")
    
    # Generate color based on title hash
    title_hash = hash(title) % 360
    hue = title_hash
    
    # Create wide, cinematic gradient
    color1_rgb = tuple(int(c * 255) for c in colorsys.hls_to_rgb(hue / 360, 0.15, 0.6))
    color2_rgb = tuple(int(c * 255) for c in colorsys.hls_to_rgb((hue + 120) / 360, 0.1, 0.4))
    
    img = _create_gradient_background(width, height, color1_rgb, color2_rgb, "horizontal")
    
    # Add dark overlay for text readability
    overlay = Image.new('RGBA', (width, height), (0, 0, 0, 100))
    img = Image.alpha_composite(img.convert('RGBA'), overlay).convert('RGB')
    
    d = ImageDraw.Draw(img)
    
    # Calculate font size (12% of height for backgrounds - more subtle)
    font_size = max(30, min(80, int(height * 0.12)))
    font, font_loaded = _load_font(font_size)
    
    # Wrap text
    max_text_width = int(width * 0.75)
    lines = _wrap_text(text, font, max_text_width)
    
    # Calculate text positioning
    if font_loaded:
        line_height = int(font_size * 1.3)
    else:
        line_height = int(font_size * 1.4)
    
    total_height = len(lines) * line_height
    start_y = (height - total_height) // 2
    
    # Draw subtle text
    text_color = (255, 255, 255)
    shadow_color = (0, 0, 0)
    shadow_offset = max(2, font_size // 30)
    
    for i, line in enumerate(lines):
        y_pos = start_y + (i * line_height)
        # Measure text
        temp_img = Image.new('RGB', (100, 100))
        temp_draw = ImageDraw.Draw(temp_img)
        bbox = temp_draw.textbbox((0, 0), line, font=font)
        text_width = bbox[2] - bbox[0]
        x_pos = (width - text_width) // 2
        
        # Draw shadow
        d.text((x_pos + shadow_offset, y_pos + shadow_offset), line, fill=shadow_color, font=font)
        # Draw text with slight transparency effect (lighter color)
        d.text((x_pos, y_pos), line, fill=text_color, font=font)
    
    byte_io = BytesIO()
    img.save(byte_io, "JPEG", quality=85)
    byte_io.seek(0)
    return byte_io

def generate_placeholder_image(
    title: str = "No Logo", 
    width: int = DEFAULT_PLACEHOLDER_WIDTH, 
    height: int = DEFAULT_PLACEHOLDER_HEIGHT, 
    monochrome: bool = False,
    image_type: str = "logo"
) -> BytesIO:
    """
    Generate a placeholder image based on image type.
    
    Args:
        title: Text to display
        width: Image width
        height: Image height
        monochrome: If True, creates grayscale (for icons)
        image_type: Type of image ("logo", "poster", "background", "icon")
        
    Returns:
        BytesIO object containing the generated image
    """
    # Route to appropriate generator based on type and dimensions
    if image_type == "logo" or (width == LOGO_WIDTH and height == LOGO_HEIGHT):
        result = generate_logo_placeholder(title, width, height)
    elif image_type == "poster" or (width == POSTER_WIDTH and height == POSTER_HEIGHT):
        result = generate_poster_placeholder(title, width, height)
    elif image_type == "background" or (width == BACKGROUND_WIDTH and height == BACKGROUND_HEIGHT):
        result = generate_background_placeholder(title, width, height)
    else:
        # Default to logo style for unknown types
        result = generate_logo_placeholder(title, width, height)
    
    # Convert to monochrome if requested
    if monochrome:
        img = Image.open(result)
        img = img.convert('L')
        byte_io = BytesIO()
        img.save(byte_io, "PNG")
        byte_io.seek(0)
        return byte_io
    
    return result

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
        logger.info(f"Generic placeholder URL detected for {tvg_id}, generating {image_type} placeholder")
        processed_image = generate_placeholder_image(title, width, height, monochrome, image_type)
        redis_store.store_processed_image(cache_key, processed_image.getvalue())
        return processed_image

    content = await fetch_image_content(redis_store, image_url)
    if not content:
        # Generate placeholder when fetch fails - use versioned cache key
        logger.info(f"Image fetch failed for {tvg_id} ({image_url[:50]}...), generating {image_type} placeholder")
        placeholder_cache_key = f"{cache_key}_placeholder_{PLACEHOLDER_CACHE_VERSION}"
        cached_placeholder = redis_store.get_processed_image(placeholder_cache_key)
        if cached_placeholder:
            logger.info(f"Returning cached placeholder for {placeholder_cache_key}")
            return BytesIO(cached_placeholder)
        
        processed_image = generate_placeholder_image(title, width, height, monochrome, image_type)
        redis_store.store_processed_image(placeholder_cache_key, processed_image.getvalue())
        return processed_image

    try:
        # Suppress PIL warning about palette images with transparency - we handle it correctly
        with warnings.catch_warnings():
            warnings.filterwarnings('ignore', category=UserWarning, module='PIL')
            original_image = Image.open(BytesIO(content))
        
        logger.debug(f"Processing image for {tvg_id}: mode={original_image.mode}, size={original_image.size}")
        
        # Handle different image modes and transparency
        # Convert palette mode images with transparency to RGBA immediately to avoid warnings
        if original_image.mode == 'P':
            # Check if palette has transparency
            if 'transparency' in original_image.info:
                logger.debug(f"Converting palette mode image {tvg_id} with transparency to RGBA")
                original_image = original_image.convert('RGBA')
            else:
                original_image = original_image.convert('RGB')
        
        # Handle transparency - preserve alpha channel if present
        has_alpha = original_image.mode in ('RGBA', 'LA') or 'transparency' in original_image.info
        if has_alpha:
            logger.debug(f"Image {tvg_id} has transparency/alpha channel")
        
        if monochrome:
            # Convert to grayscale, handling transparency
            if has_alpha:
                # Create a white background for transparency
                bg = Image.new('RGB', original_image.size, (255, 255, 255))
                if original_image.mode == 'RGBA':
                    bg.paste(original_image, mask=original_image.split()[3])  # Use alpha channel as mask
                elif original_image.mode == 'LA':
                    bg.paste(original_image.convert('RGB'), mask=original_image.split()[1])
                else:
                    bg.paste(original_image)
                original_image = bg.convert("L")
            else:
                original_image = original_image.convert("L")
        else:
            # Convert to RGB, handling transparency
            if has_alpha:
                # Use black background for all image types to ensure white text/elements are visible
                bg_color = (0, 0, 0)  # Black background
                
                bg = Image.new('RGB', original_image.size, bg_color)
                if original_image.mode == 'RGBA':
                    bg.paste(original_image, mask=original_image.split()[3])  # Use alpha channel as mask
                elif original_image.mode == 'LA':
                    # LA mode: L (luminance) + A (alpha)
                    bg.paste(original_image.convert('RGB'), mask=original_image.split()[1])
                else:
                    bg.paste(original_image)
                original_image = bg
            else:
                original_image = original_image.convert("RGB")

        original_width, original_height = original_image.size

        # Calculate resize ratio to fit within target dimensions while maintaining aspect ratio
        ratio = min(width / original_width, height / original_height)
        new_width = int(original_width * ratio)
        new_height = int(original_height * ratio)

        # Resize with high-quality resampling
        resized_image = original_image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        logger.debug(f"Resized {tvg_id} from {original_width}x{original_height} to {new_width}x{new_height}, mode={resized_image.mode}")

        # Create black background for all image types to ensure white text/elements are visible
        bg_color = (0, 0, 0)  # Black background for all types
        
        if monochrome:
            background = Image.new('L', (width, height), 0)  # Black for monochrome too
        else:
            background = Image.new('RGB', (width, height), bg_color)

        # Center the resized image on the background
        paste_x = (width - new_width) // 2
        paste_y = (height - new_height) // 2

        # Paste the resized image onto the background
        # Ensure we're pasting the actual image content, not just a color
        # Note: resized_image should be RGB at this point (we converted earlier), but check anyway
        if resized_image.mode in ('RGBA', 'LA'):
            logger.debug(f"Pasting {tvg_id} image with alpha channel mask at ({paste_x}, {paste_y})")
            # Use the alpha channel as mask for proper transparency handling
            background.paste(resized_image, (paste_x, paste_y), resized_image.split()[3] if resized_image.mode == 'RGBA' else resized_image.split()[1])
        elif resized_image.mode == 'RGB':
            logger.debug(f"Pasting {tvg_id} RGB image at ({paste_x}, {paste_y})")
            # Direct paste for RGB images - this preserves all colors including white
            background.paste(resized_image, (paste_x, paste_y))
        else:
            # Convert to RGB if it's in an unexpected mode
            logger.warning(f"Unexpected image mode {resized_image.mode} for {tvg_id}, converting to RGB")
            resized_image = resized_image.convert('RGB')
            background.paste(resized_image, (paste_x, paste_y))
        
        logger.debug(f"Pasted {tvg_id} image onto {image_type} background ({width}x{height})")

        byte_io = BytesIO()
        # Use PNG for all images to preserve quality and avoid JPEG compression artifacts
        # PNG ensures perfect color preservation including white pixels
        format = "PNG"
        background.save(byte_io, format)
        byte_io.seek(0)
        logger.info(f"Successfully processed {image_type} image for {tvg_id}: {len(byte_io.getvalue())} bytes, format={format}")
        redis_store.store_processed_image(cache_key, byte_io.getvalue())
        return byte_io
    except UnidentifiedImageError:
        # Generate placeholder when image can't be identified - use versioned cache key
        logger.info(f"Unidentified image format for {tvg_id}, generating {image_type} placeholder")
        placeholder_cache_key = f"{cache_key}_placeholder_{PLACEHOLDER_CACHE_VERSION}"
        cached_placeholder = redis_store.get_processed_image(placeholder_cache_key)
        if cached_placeholder:
            return BytesIO(cached_placeholder)
        processed_image = generate_placeholder_image(title, width, height, monochrome, image_type)
        redis_store.store_processed_image(placeholder_cache_key, processed_image.getvalue())
        return processed_image
    except Exception as e:
        logger.error(f"Error processing image for URL: {image_url} - {e}")
        logger.info(f"Generating {image_type} placeholder for {tvg_id} due to processing error")
        # Generate placeholder on error - use versioned cache key
        placeholder_cache_key = f"{cache_key}_placeholder_{PLACEHOLDER_CACHE_VERSION}"
        cached_placeholder = redis_store.get_processed_image(placeholder_cache_key)
        if cached_placeholder:
            return BytesIO(cached_placeholder)
        processed_image = generate_placeholder_image(title, width, height, monochrome, image_type)
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
