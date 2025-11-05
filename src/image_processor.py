import os
import httpx
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError
import logging

logger = logging.getLogger(__name__)

# Define the generic placeholder URL
GENERIC_PLACEHOLDER_URL = "https://via.placeholder.com/240x135.png?text=No+Logo"

# Function to generate a default "No Logo" image
def generate_no_logo_image(title: str = "No Logo") -> BytesIO:
    target_width, target_height = 300, 450
    img = Image.new('RGB', (target_width, target_height), color = (0, 0, 0)) # Black background
    d = ImageDraw.Draw(img)
    
    try:
        # Try to load a font, fallback to default if not found
        font_path = "resources/fonts/IBMPlexSans-Medium.ttf" # Assuming a font exists here
        if os.path.exists(font_path):
            font = ImageFont.truetype(font_path, 40)
        else:
            font = ImageFont.load_default()
    except Exception:
        font = ImageFont.load_default()

    # Use the provided title instead of hardcoded "No Logo"
    text = title
    # Calculate text size and position to center it
    bbox = d.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    x = (target_width - text_width) / 2
    y = (target_height - text_height) / 2

    d.text((x, y), text, fill=(255, 255, 255), font=font) # White text
    
    byte_io = BytesIO()
    img.save(byte_io, "JPEG", quality=85)
    byte_io.seek(0)
    return byte_io

async def fetch_image_content(url: str) -> bytes:
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=10, follow_redirects=True)
            response.raise_for_status()
            if not response.headers["Content-Type"].lower().startswith("image/"):
                raise ValueError(f"Unexpected content type: {response.headers['Content-Type']}")
            return response.content
    except httpx.RequestError as e:
        logger.warning(f"Error fetching image from {url}: {e}")
        return b''
    except ValueError as e:
        logger.warning(f"Error fetching image from {url}: {e}")
        return b''

async def process_image(image_url: str, title: str = "No Title") -> BytesIO:
    # Check for the generic placeholder URL first
    if image_url == GENERIC_PLACEHOLDER_URL:
        return generate_no_logo_image(title)

    content = await fetch_image_content(image_url)
    if not content:
        # If fetching fails, also return the generated "No Logo" image
        return generate_no_logo_image(title)

    try:
        original_image = Image.open(BytesIO(content)).convert("RGB")

        target_width, target_height = 300, 450
        original_width, original_height = original_image.size

        # Calculate the ratio to fit within the target dimensions
        ratio = min(target_width / original_width, target_height / original_height)
        new_width = int(original_width * ratio)
        new_height = int(original_height * ratio)

        # Resize the image while maintaining aspect ratio
        resized_image = original_image.resize((new_width, new_height), Image.Resampling.LANCZOS)

        # Create a new black background canvas
        background = Image.new('RGB', (target_width, target_height), (0, 0, 0))

        # Calculate position to paste the resized image so it's centered
        paste_x = (target_width - new_width) // 2
        paste_y = (target_height - new_height) // 2

        # Paste the resized image onto the background
        background.paste(resized_image, (paste_x, paste_y))

        byte_io = BytesIO()
        background.save(byte_io, "JPEG", quality=85)
        byte_io.seek(0)
        return byte_io
    except UnidentifiedImageError:
        logger.warning(f"Cannot identify image from provided content for URL: {image_url}")
        return generate_no_logo_image(title) # Return generated image on error
    except Exception as e:
        logger.error(f"Error processing image for URL: {image_url} - {e}")
        return generate_no_logo_image(title) # Return generated image on error
