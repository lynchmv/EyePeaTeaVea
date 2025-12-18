import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import pytest
from unittest.mock import Mock, patch, AsyncMock
from io import BytesIO
from PIL import Image
from src.image_processor import (
    generate_placeholder_image,
    fetch_image_content,
    process_image,
    get_poster,
    get_background,
    get_logo,
    get_icon,
    GENERIC_PLACEHOLDER_URL
)

class TestImageProcessor:

    def test_generate_placeholder_image_default(self):
        """Test generating a default placeholder image."""
        img_bytes = generate_placeholder_image()
        
        assert isinstance(img_bytes, BytesIO)
        img_bytes.seek(0)
        img = Image.open(img_bytes)
        assert img.size == (500, 750)
        assert img.mode == 'RGB'

    def test_generate_placeholder_image_custom(self):
        """Test generating a placeholder image with custom parameters."""
        img_bytes = generate_placeholder_image(title="Test Channel", width=800, height=600)
        
        assert isinstance(img_bytes, BytesIO)
        img_bytes.seek(0)
        img = Image.open(img_bytes)
        assert img.size == (800, 600)

    def test_generate_placeholder_image_monochrome(self):
        """Test generating a monochrome placeholder image."""
        img_bytes = generate_placeholder_image(monochrome=True)
        
        assert isinstance(img_bytes, BytesIO)
        img_bytes.seek(0)
        img = Image.open(img_bytes)
        assert img.mode == 'L'  # Grayscale

    @pytest.mark.asyncio
    async def test_fetch_image_content_cached(self):
        """Test fetching image content from cache."""
        mock_redis_store = Mock()
        cached_content = b"cached_image_data"
        mock_redis_store.get.return_value = cached_content
        
        result = await fetch_image_content(mock_redis_store, "http://example.com/image.png")
        
        assert result == cached_content
        mock_redis_store.get.assert_called_once_with("image_cache:http://example.com/image.png")

    @pytest.mark.asyncio
    async def test_fetch_image_content_http_success(self):
        """Test fetching image content from HTTP successfully."""
        mock_redis_store = Mock()
        mock_redis_store.get.return_value = None  # Not cached
        
        mock_response = Mock()
        mock_response.headers = {"Content-Type": "image/png"}
        mock_response.content = b"image_data"
        mock_response.raise_for_status = Mock()
        
        with patch('src.image_processor.httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
            
            result = await fetch_image_content(mock_redis_store, "http://example.com/image.png")
            
            assert result == b"image_data"
            mock_redis_store.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_image_content_http_error(self):
        """Test fetching image content when HTTP request fails."""
        mock_redis_store = Mock()
        mock_redis_store.get.return_value = None
        
        import httpx
        with patch('src.image_processor.httpx.AsyncClient') as mock_client:
            # Mock RequestError which is what httpx raises
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(side_effect=httpx.RequestError("Connection error"))
            
            result = await fetch_image_content(mock_redis_store, "http://example.com/image.png")
            
            assert result == b''

    @pytest.mark.asyncio
    async def test_process_image_cached(self):
        """Test processing image when cached."""
        mock_redis_store = Mock()
        cached_image = b"cached_processed_image"
        mock_redis_store.get_processed_image.return_value = cached_image
        
        result = await process_image(
            mock_redis_store,
            "CNN",
            "http://example.com/logo.png",
            "CNN",
            500,
            750,
            "poster"
        )
        
        assert isinstance(result, BytesIO)
        assert result.getvalue() == cached_image
        mock_redis_store.get_processed_image.assert_called_once_with("CNN_poster")

    @pytest.mark.asyncio
    async def test_process_image_generic_placeholder(self):
        """Test processing image with generic placeholder URL."""
        mock_redis_store = Mock()
        mock_redis_store.get_processed_image.return_value = None
        
        result = await process_image(
            mock_redis_store,
            "CNN",
            GENERIC_PLACEHOLDER_URL,
            "CNN",
            500,
            750,
            "poster"
        )
        
        assert isinstance(result, BytesIO)
        mock_redis_store.store_processed_image.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_image_fetch_fails(self):
        """Test processing image when fetch fails."""
        mock_redis_store = Mock()
        mock_redis_store.get_processed_image.return_value = None
        
        with patch('src.image_processor.fetch_image_content', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = b''  # Fetch fails (returns empty bytes)
            
            result = await process_image(
                mock_redis_store,
                "CNN",
                "http://example.com/logo.png",
                "CNN",
                500,
                750,
                "poster"
            )
            
            assert isinstance(result, BytesIO)
            # When fetch returns empty bytes, process_image checks `if not content:` 
            # and returns generate_placeholder_image() directly without storing it
            # (Only generic placeholder URLs get stored, not failed fetches)
            mock_fetch.assert_called_once()
            # Verify that store_processed_image was NOT called (failed fetches aren't cached)
            assert not mock_redis_store.store_processed_image.called, "Failed fetches should not be cached"

    @pytest.mark.asyncio
    async def test_get_poster(self):
        """Test get_poster function."""
        mock_redis_store = Mock()
        mock_redis_store.get_processed_image.return_value = None
        
        with patch('src.image_processor.fetch_image_content', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = b''
            
            result = await get_poster(mock_redis_store, "CNN", "http://example.com/logo.png", "CNN")
            
            assert isinstance(result, BytesIO)
            mock_redis_store.get_processed_image.assert_called_once_with("CNN_poster")

    @pytest.mark.asyncio
    async def test_get_background(self):
        """Test get_background function."""
        mock_redis_store = Mock()
        mock_redis_store.get_processed_image.return_value = None
        
        with patch('src.image_processor.fetch_image_content', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = b''
            
            result = await get_background(mock_redis_store, "CNN", "http://example.com/logo.png", "CNN")
            
            assert isinstance(result, BytesIO)
            mock_redis_store.get_processed_image.assert_called_once_with("CNN_background")

    @pytest.mark.asyncio
    async def test_get_logo(self):
        """Test get_logo function."""
        mock_redis_store = Mock()
        mock_redis_store.get_processed_image.return_value = None
        
        with patch('src.image_processor.fetch_image_content', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = b''
            
            result = await get_logo(mock_redis_store, "CNN", "http://example.com/logo.png", "CNN")
            
            assert isinstance(result, BytesIO)
            mock_redis_store.get_processed_image.assert_called_once_with("CNN_logo")

    @pytest.mark.asyncio
    async def test_get_icon(self):
        """Test get_icon function (monochrome)."""
        mock_redis_store = Mock()
        mock_redis_store.get_processed_image.return_value = None
        
        with patch('src.image_processor.fetch_image_content', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = b''
            
            result = await get_icon(mock_redis_store, "CNN", "http://example.com/logo.png", "CNN")
            
            assert isinstance(result, BytesIO)
            mock_redis_store.get_processed_image.assert_called_once_with("CNN_icon")

