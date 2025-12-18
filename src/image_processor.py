import os
import httpx
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError
import logging
from .redis_store import RedisStore

logger = logging.getLogger(__name__)

# Define the generic placeholder URL
GENERIC_PLACEHOLDER_URL = "https://via.placeholder.com/240x135.png?text=No+Logo"

# Function to generate a default placeholder image
def generate_placeholder_image(title: str = "No Logo", width: int = 500, height: int = 750, monochrome: bool = False) -> BytesIO:
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
    cache_key = f"image_cache:{url}"
    cached_content = redis_store.get(cache_key)
    if cached_content:
        logger.info(f"Returning cached image content for {url}")
        return cached_content

    try:
        async with httpx.AsyncClient() as client:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"}
            response = await client.get(url, headers=headers, timeout=10, follow_redirects=True)
            response.raise_for_status()
            if not response.headers["Content-Type"].lower().startswith("image/"):
                raise ValueError(f"Unexpected content type: {response.headers['Content-Type']}")
            
            content = response.content
            redis_store.set(cache_key, content, expiration_time=60*60*24*7) # Cache for 7 days
            return content
    except httpx.HTTPStatusError as e:
        logger.warning(f"HTTP status error fetching image from {url}: {e}")
        return b''
    except httpx.RequestError as e:
        logger.warning(f"Error fetching image from {url}: {e}")
        return b''
    except ValueError as e:
        logger.warning(f"Error fetching image from {url}: {e}")
        return b''

async def process_image(redis_store: RedisStore, tvg_id: str, image_url: str, title: str, width: int, height: int, image_type: str, monochrome: bool = False) -> BytesIO:
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
    return await process_image(redis_store, tvg_id, image_url, title, 500, 750, "poster")

async def get_background(redis_store: RedisStore, tvg_id: str, image_url: str, title: str) -> BytesIO:
    return await process_image(redis_store, tvg_id, image_url, title, 1024, 576, "background")

async def get_logo(redis_store: RedisStore, tvg_id: str, image_url: str, title: str) -> BytesIO:
    return await process_image(redis_store, tvg_id, image_url, title, 500, 500, "logo")

async def get_icon(redis_store: RedisStore, tvg_id: str, image_url: str, title: str) -> BytesIO:
    return await process_image(redis_store, tvg_id, image_url, title, 256, 256, "icon", monochrome=True)
