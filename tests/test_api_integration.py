import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import unittest
import pytest
from fastapi.testclient import TestClient
import os
import json
from unittest.mock import patch

from src.main import app
from src.redis_store import RedisStore
from src.models import UserData

@pytest.fixture(scope="function")
def redis_store_fixture():
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    store = RedisStore(redis_url)
    # Ensure a clean state for tests
    store.redis_client.flushdb()
    # Clear rate limits
    for key in store.redis_client.scan_iter("rate_limit:*"):
        store.redis_client.delete(key)
    return store

def test_configure_and_get_manifest(redis_store_fixture: RedisStore):
    with TestClient(app) as client:
        m3u_sources = ["http://example.com/playlist.m3u"]
        host_url = "http://test-host.com"
        addon_password = "testpass"

        response = client.post(
            "/configure",
            json={
                "m3u_sources": m3u_sources,
                "host_url": host_url,
                "addon_password": addon_password
            }
        )
        assert response.status_code == 200
        config_data = response.json()
        secret_str = config_data["secret_str"]
        assert secret_str is not None

        # Verify UserData in Redis
        user_data = redis_store_fixture.get_user_data(secret_str)
        assert user_data is not None
        assert user_data.m3u_sources == m3u_sources
        assert str(user_data.host_url) == host_url + "/"
        assert user_data.addon_password == addon_password

        # Test manifest endpoint with valid secret_str
        response = client.get(f"/{secret_str}/manifest.json")
        assert response.status_code == 200
        manifest = response.json()
        assert manifest["id"] == "org.stremio.eyepeateavea"

        response = client.get(f"/invalid_secret/manifest.json")
        assert response.status_code == 404

def test_configure_invalid_data(redis_store_fixture: RedisStore):
    with TestClient(app) as client:
        # Test with missing m3u_sources
        response = client.post(
            "/configure",
            json={
                "host_url": "http://test-host.com",
                "addon_password": "testpass"
            }
        )
        assert response.status_code == 422

        # Test with invalid m3u_sources (not a list)
        response = client.post(
            "/configure",
            json={
                "m3u_sources": "http://example.com/playlist.m3u",
                "host_url": "http://test-host.com",
                "addon_password": "testpass"
            }
        )
        assert response.status_code == 422

        # Test with invalid cron expression (too few fields)
        response = client.post(
            "/configure",
            json={
                "m3u_sources": ["http://example.com/playlist.m3u"],
                "parser_schedule_crontab": "0 0",
                "host_url": "http://test-host.com"
            }
        )
        assert response.status_code == 422
        assert "cron expression" in response.json()["detail"][0]["msg"].lower()

        # Test with invalid cron expression (invalid field value)
        response = client.post(
            "/configure",
            json={
                "m3u_sources": ["http://example.com/playlist.m3u"],
                "parser_schedule_crontab": "60 0 * * *",  # Invalid: minute > 59
                "host_url": "http://test-host.com"
            }
        )
        assert response.status_code == 422
        assert "cron expression" in response.json()["detail"][0]["msg"].lower()

        # Test with invalid host_url (not a valid URL)
        response = client.post(
            "/configure",
            json={
                "m3u_sources": ["http://example.com/playlist.m3u"],
                "host_url": "not-a-url",
                "addon_password": "testpass"
            }
        )
        assert response.status_code == 422
        
        # Test with invalid M3U source URL (not a valid URL)
        response = client.post(
            "/configure",
            json={
                "m3u_sources": ["not-a-url"],
                "host_url": "http://test-host.com"
            }
        )
        assert response.status_code == 422
        assert "invalid url" in response.json()["detail"][0]["msg"].lower()
        
        # Test with empty M3U source
        response = client.post(
            "/configure",
            json={
                "m3u_sources": [""],
                "host_url": "http://test-host.com"
            }
        )
        assert response.status_code == 422
        
        # Test with too many M3U sources (over limit)
        too_many_sources = [f"http://example.com/playlist{i}.m3u" for i in range(51)]
        response = client.post(
            "/configure",
            json={
                "m3u_sources": too_many_sources,
                "host_url": "http://test-host.com"
            }
        )
        assert response.status_code == 422
        error_msg = response.json()["detail"][0]["msg"].lower()
        assert "at most" in error_msg or "maximum" in error_msg
        
        # Test with unsupported URL scheme (ftp)
        response = client.post(
            "/configure",
            json={
                "m3u_sources": ["ftp://example.com/playlist.m3u"],
                "host_url": "http://test-host.com"
            }
        )
        assert response.status_code == 422
        assert "unsupported scheme" in response.json()["detail"][0]["msg"].lower()

def test_update_configure(redis_store_fixture: RedisStore):
    with TestClient(app) as client:
        # First, create a configuration
        response = client.post(
            "/configure",
            json={
                "m3u_sources": ["http://example.com/playlist1.m3u"],
                "parser_schedule_crontab": "0 */6 * * *",
                "host_url": "http://test-host.com",
                "addon_password": "original_password"
            }
        )
        assert response.status_code == 200
        secret_str = response.json()["secret_str"]
        
        # Verify original configuration
        original_user_data = redis_store_fixture.get_user_data(secret_str)
        assert original_user_data.m3u_sources == ["http://example.com/playlist1.m3u"]
        assert original_user_data.parser_schedule_crontab == "0 */6 * * *"
        assert original_user_data.addon_password == "original_password"
        
        # Update only m3u_sources
        response = client.put(
            f"/{secret_str}/configure",
            json={
                "m3u_sources": ["http://example.com/playlist2.m3u", "http://example.com/playlist3.m3u"]
            }
        )
        assert response.status_code == 200
        result = response.json()
        assert result["secret_str"] == secret_str
        assert result["updated_fields"]["m3u_sources"] == True
        assert result["updated_fields"]["parser_schedule_crontab"] == False
        
        # Verify updated configuration
        updated_user_data = redis_store_fixture.get_user_data(secret_str)
        assert updated_user_data.m3u_sources == ["http://example.com/playlist2.m3u", "http://example.com/playlist3.m3u"]
        assert updated_user_data.parser_schedule_crontab == "0 */6 * * *"  # Unchanged
        assert updated_user_data.addon_password == "original_password"  # Unchanged
        
        # Update cron expression and password
        response = client.patch(
            f"/{secret_str}/configure",
            json={
                "parser_schedule_crontab": "0 0 * * *",
                "addon_password": "new_password"
            }
        )
        assert response.status_code == 200
        
        # Verify updated configuration
        updated_user_data = redis_store_fixture.get_user_data(secret_str)
        assert updated_user_data.m3u_sources == ["http://example.com/playlist2.m3u", "http://example.com/playlist3.m3u"]  # Unchanged
        assert updated_user_data.parser_schedule_crontab == "0 0 * * *"  # Updated
        assert updated_user_data.addon_password == "new_password"  # Updated
        
        # Test update with invalid secret_str
        response = client.put(
            "/invalid_secret/configure",
            json={
                "m3u_sources": ["http://example.com/playlist.m3u"]
            }
        )
        assert response.status_code == 404
        
        # Test update with invalid cron expression
        response = client.put(
            f"/{secret_str}/configure",
            json={
                "parser_schedule_crontab": "invalid cron"
            }
        )
        assert response.status_code == 422
        
        # Test removing password (set to empty string)
        response = client.put(
            f"/{secret_str}/configure",
            json={
                "addon_password": ""
            }
        )
        assert response.status_code == 200
        updated_user_data = redis_store_fixture.get_user_data(secret_str)
        assert updated_user_data.addon_password is None

def test_catalog_meta_stream_endpoints(redis_store_fixture: RedisStore):
    with TestClient(app) as client:
        # Configure a user first
        m3u_sources = ["http://example.com/playlist.m3u"]
        host_url = "http://test-host.com"
        addon_password = "testpass"

        response = client.post(
            "/configure",
            json={
                "m3u_sources": m3u_sources,
                "host_url": host_url,
                "addon_password": addon_password
            }
        )
        secret_str = response.json()["secret_str"]

        # Mock some channels and programs in Redis for testing catalog, meta, stream
        sample_channel = {
            "group_title": "News",
            "tvg_id": "CNN",
            "tvg_name": "CNN",
            "tvg_logo": "cnn.png",
            "url_tvg": "",
            "stream_url": "http://cnn.com/live"
        }
        redis_store_fixture.store_channels(secret_str, [sample_channel])

        # Test catalog endpoint
        response = client.get(f"/{secret_str}/catalog/tv/iptv_tv.json")
        assert response.status_code == 200
        catalog = response.json()
        assert len(catalog["metas"]) > 0
        assert catalog["metas"][0]["id"] == "eyepeateaveaCNN"

        # Test meta endpoint
        response = client.get(f"/{secret_str}/meta/tv/eyepeateaveaCNN.json")
        assert response.status_code == 200
        meta = response.json()
        assert meta["meta"]["name"] == "CNN"
        assert "poster" in meta["meta"]

        # Test stream endpoint
        response = client.get(f"/{secret_str}/stream/tv/eyepeateaveaCNN.json")
        assert response.status_code == 200
        stream = response.json()
        assert stream["streams"][0]["url"] == "http://cnn.com/live"
        # Test endpoints with invalid secret_str
        response = client.get(f"/invalid_secret/catalog/tv/iptv_tv.json")
        assert response.status_code == 404
        response = client.get(f"/invalid_secret/meta/tv/eyepeateavea:CNN.json")
        assert response.status_code == 404
        response = client.get(f"/invalid_secret/stream/tv/eyepeateavea:CNN.json")
        assert response.status_code == 404

def test_catalog_events(redis_store_fixture: RedisStore):
    with TestClient(app) as client:
        # Configure a user first
        m3u_sources = ["http://example.com/playlist.m3u"]
        host_url = "http://test-host.com"
        addon_password = "testpass"

        response = client.post(
            "/configure",
            json={
                "m3u_sources": m3u_sources,
                "host_url": host_url,
                "addon_password": addon_password
            }
        )
        secret_str = response.json()["secret_str"]

        # Mock some event channels in Redis
        sample_event = {
            "group_title": "Sports",
            "tvg_id": "ESPN",
            "tvg_name": "ESPN",
            "tvg_logo": "espn.png",
            "url_tvg": "",
            "stream_url": "http://espn.com/live",
            "is_event": True,
            "event_title": "Live: NBA Finals",
            "event_sport": "Basketball"
        }
        redis_store_fixture.store_channels(secret_str, [sample_event])

        # Test events catalog endpoint
        response = client.get(f"/{secret_str}/catalog/events/iptv_sports_events.json")
        assert response.status_code == 200
        catalog = response.json()
        assert len(catalog["metas"]) > 0
        assert catalog["metas"][0]["name"] == "Live: NBA Finals"

        # Test genre filtering
        response = client.get(f"/{secret_str}/catalog/events/iptv_sports_events/genre=Basketball.json")
        assert response.status_code == 200
        catalog = response.json()
        assert len(catalog["metas"]) > 0
        assert catalog["metas"][0]["name"] == "Live: NBA Finals"

        # Test genre filtering with no results
        response = client.get(f"/{secret_str}/catalog/events/iptv_sports_events/genre=Soccer.json")
        assert response.status_code == 200
        catalog = response.json()
        assert len(catalog["metas"]) == 0

        # Test search filtering
        response = client.get(f"/{secret_str}/catalog/events/iptv_sports_events/search=NBA.json")
        assert response.status_code == 200
        catalog = response.json()
        assert len(catalog["metas"]) > 0
        assert catalog["metas"][0]["name"] == "Live: NBA Finals"

        # Test search filtering with no results
        response = client.get(f"/{secret_str}/catalog/events/iptv_sports_events/search=NFL.json")
        assert response.status_code == 200
        catalog = response.json()
        assert len(catalog["metas"]) == 0

def test_health_endpoint(redis_store_fixture: RedisStore):
    """Test the health check endpoint."""
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        health_data = response.json()
        assert "status" in health_data
        assert "redis" in health_data
        assert "service" in health_data
        assert health_data["service"] == "EyePeaTeaVea"
        # Redis should be connected in test environment
        assert health_data["redis"] == "connected"
        assert health_data["status"] == "healthy"

def test_rate_limiting(redis_store_fixture: RedisStore):
    """Test rate limiting on /configure endpoint."""
    with TestClient(app) as client:
        # Make 10 requests (the limit)
        for i in range(10):
            response = client.post(
                "/configure",
                json={
                    "m3u_sources": [f"http://example.com/playlist{i}.m3u"],
                    "host_url": "http://test-host.com"
                }
            )
            # All should succeed
            assert response.status_code in [200, 422]  # 422 for validation errors is OK
        
        # 11th request should be rate limited
        response = client.post(
            "/configure",
            json={
                "m3u_sources": ["http://example.com/playlist11.m3u"],
                "host_url": "http://test-host.com"
            }
        )
        assert response.status_code == 429
        assert "rate limit" in response.json()["detail"].lower()

def test_get_config_endpoint(redis_store_fixture: RedisStore):
    """Test the GET /{secret_str}/config endpoint."""
    with TestClient(app) as client:
        # First, create a configuration
        response = client.post(
            "/configure",
            json={
                "m3u_sources": ["http://example.com/playlist.m3u"],
                "parser_schedule_crontab": "0 */6 * * *",
                "host_url": "http://test-host.com",
                "addon_password": "testpass"
            }
        )
        assert response.status_code == 200
        secret_str = response.json()["secret_str"]
        
        # Get the configuration
        response = client.get(f"/{secret_str}/config")
        assert response.status_code == 200
        config = response.json()
        assert config["m3u_sources"] == ["http://example.com/playlist.m3u"]
        assert config["parser_schedule_crontab"] == "0 */6 * * *"
        assert config["host_url"] == "http://test-host.com/"
        assert config["addon_password"] == "testpass"
        
        # Test with invalid secret_str
        response = client.get("/invalid_secret/config")
        assert response.status_code == 404

def test_empty_catalog(redis_store_fixture: RedisStore):
    """Test catalog endpoints with no channels."""
    with TestClient(app) as client:
        # Configure a user but don't add any channels
        response = client.post(
            "/configure",
            json={
                "m3u_sources": ["http://example.com/playlist.m3u"],
                "host_url": "http://test-host.com"
            }
        )
        secret_str = response.json()["secret_str"]
        
        # Test TV catalog with no channels
        response = client.get(f"/{secret_str}/catalog/tv/iptv_tv.json")
        assert response.status_code == 200
        catalog = response.json()
        assert catalog["metas"] == []
        
        # Test events catalog with no channels
        response = client.get(f"/{secret_str}/catalog/events/iptv_sports_events.json")
        assert response.status_code == 200
        catalog = response.json()
        assert catalog["metas"] == []

def test_stream_endpoint_no_channel(redis_store_fixture: RedisStore):
    """Test stream endpoint when channel doesn't exist."""
    with TestClient(app) as client:
        # Configure a user
        response = client.post(
            "/configure",
            json={
                "m3u_sources": ["http://example.com/playlist.m3u"],
                "host_url": "http://test-host.com"
            }
        )
        secret_str = response.json()["secret_str"]
        
        # Try to get stream for non-existent channel
        response = client.get(f"/{secret_str}/stream/tv/eyepeateaveaNonexistent.json")
        # Stream endpoint returns 404 when channel not found
        assert response.status_code == 404

def test_meta_endpoint_no_channel(redis_store_fixture: RedisStore):
    """Test meta endpoint when channel doesn't exist."""
    with TestClient(app) as client:
        # Configure a user
        response = client.post(
            "/configure",
            json={
                "m3u_sources": ["http://example.com/playlist.m3u"],
                "host_url": "http://test-host.com"
            }
        )
        secret_str = response.json()["secret_str"]
        
        # Try to get meta for non-existent channel
        response = client.get(f"/{secret_str}/meta/tv/eyepeateaveaNonexistent.json")
        # Meta endpoint returns 404 when channel not found
        assert response.status_code == 404

def test_catalog_filtering_edge_cases(redis_store_fixture: RedisStore):
    """Test catalog filtering with edge cases."""
    with TestClient(app) as client:
        # Configure a user
        response = client.post(
            "/configure",
            json={
                "m3u_sources": ["http://example.com/playlist.m3u"],
                "host_url": "http://test-host.com"
            }
        )
        secret_str = response.json()["secret_str"]
        
        # Store channels with various edge cases
        channels = [
            {
                "group_title": "News",
                "tvg_id": "CNN",
                "tvg_name": "CNN",
                "tvg_logo": "",
                "url_tvg": "",
                "stream_url": "http://cnn.com/live",
                "is_event": False
            },
            {
                "group_title": "",  # Empty group title
                "tvg_id": "NOGROUP",
                "tvg_name": "No Group",
                "tvg_logo": "",
                "url_tvg": "",
                "stream_url": "http://nogroup.com/live",
                "is_event": False
            }
        ]
        redis_store_fixture.store_channels(secret_str, channels)
        
        # Test filtering with empty genre
        response = client.get(f"/{secret_str}/catalog/tv/iptv_tv/genre=.json")
        assert response.status_code == 200
        
        # Test filtering with special characters in search (URL encoded)
        import urllib.parse
        search_term = urllib.parse.quote("@#$%")
        response = client.get(f"/{secret_str}/catalog/tv/iptv_tv/search={search_term}.json")
        assert response.status_code == 200
        catalog = response.json()
        assert "metas" in catalog
