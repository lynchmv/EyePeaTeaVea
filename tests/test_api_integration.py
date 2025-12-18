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

@pytest.fixture(scope="module")
def redis_store_fixture():
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    store = RedisStore(redis_url)
    # Ensure a clean state for tests
    store.redis_client.flushdb()
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
