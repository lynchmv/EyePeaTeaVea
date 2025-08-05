import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import textwrap

import aiohttp
from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError

from stremio_addon.core.config import settings
from stremio_addon.db.models import MediaFusionMetaData
from stremio_addon.db.redis_database import REDIS_ASYNC_CLIENT

executor = ThreadPoolExecutor(max_workers=4)

# Pre-load fonts for efficiency
try:
    FONT_CACHE = {
        "bold_50": ImageFont.truetype("stremio_addon/static/fonts/IBMPlexSans-Bold.ttf", 50),
    }
    WATERMARK_LOGO = Image.open("stremio_addon/static/images/logo.png")
except FileNotFoundError:
    logging.error("Font or logo files not found. Please ensure they are in the static directory.")
    FONT_CACHE = {}
    WATERMARK_LOGO = None


async def fetch_poster_image(url: str) -> bytes:
    cached_image = await REDIS_ASYNC_CLIENT.get(url)
    if cached_image:
        return cached_image

    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=30) as response:
            response.raise_for_status()
            content = await response.read()
            await REDIS_ASYNC_CLIENT.set(url, content, ex=3600) # Cache for 1 hour
            return content

def get_text_color_for_background(image: Image.Image, area: tuple) -> tuple:
    cropped = image.crop(area).resize((1, 1), Image.Resampling.LANCZOS)
    avg_color = cropped.getpixel((0, 0))
    brightness = (avg_color[0] * 299 + avg_color[1] * 587 + avg_color[2] * 114) / 1000
    return ("black", "white") if brightness > 128 else ("white", "black")

def add_title_to_poster(image: Image.Image, title_text: str) -> Image.Image:
    if not FONT_CACHE:
        return image

    draw = ImageDraw.Draw(image)
    max_width_px = image.width - 40

    font = FONT_CACHE["bold_50"]
    avg_char_width = font.getlength("a")
    max_chars_per_line = int(max_width_px / avg_char_width) if avg_char_width > 0 else 20

    wrapped_lines = textwrap.wrap(title_text, width=max_chars_per_line, max_lines=3, placeholder="...")

    text_block_height = len(wrapped_lines) * (font.size + 5)
    y_position = (image.height - text_block_height) / 2

    text_color, outline_color = get_text_color_for_background(image, (20, y_position, image.width - 20, y_position + text_block_height))

    for line in wrapped_lines:
        line_width = draw.textlength(line, font=font)
        x_position = (image.width - line_width) / 2

        for dx, dy in [(-1,-1), (-1,1), (1,-1), (1,1)]:
            draw.text((x_position+dx, y_position+dy), line, font=font, fill=outline_color)
        draw.text((x_position, y_position), line, font=font, fill=text_color)

        y_position += font.size + 5

    return image

def process_poster_image(content: bytes, mediafusion_data: MediaFusionMetaData) -> BytesIO:
    try:
        original_image = Image.open(BytesIO(content)).convert("RGB")

        target_width, target_height = 300, 450
        original_width, original_height = original_image.size

        ratio = min(target_width / original_width, target_height / original_height)
        new_width = int(original_width * ratio)
        new_height = int(original_height * ratio)

        resized_image = original_image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        background = Image.new('RGB', (target_width, target_height), (0, 0, 0))
        paste_x = (target_width - new_width) // 2
        paste_y = (target_height - new_height) // 2
        background.paste(resized_image, (paste_x, paste_y))

        image = background

        if WATERMARK_LOGO:
            aspect_ratio = WATERMARK_LOGO.width / WATERMARK_LOGO.height
            new_width = int(image.width * 0.4)
            watermark_resized = WATERMARK_LOGO.resize((new_width, int(new_width / aspect_ratio)))
            watermark_position = (image.width - watermark_resized.width - 10, 10)
            image.paste(watermark_resized, watermark_position, watermark_resized)

        byte_io = BytesIO()
        image.save(byte_io, "JPEG", quality=85)
        byte_io.seek(0)
        return byte_io
    except UnidentifiedImageError:
        raise ValueError("Cannot identify image from provided content")

async def create_poster(mediafusion_data: MediaFusionMetaData) -> BytesIO:
    if not mediafusion_data.poster:
        raise ValueError("No poster URL provided")

    content = await fetch_poster_image(mediafusion_data.poster)

    loop = asyncio.get_running_loop()
    byte_io = await loop.run_in_executor(
        executor, process_poster_image, content, mediafusion_data
    )
    return byte_io

