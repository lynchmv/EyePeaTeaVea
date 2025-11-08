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
        assert user_data.host_url == host_url
        assert user_data.addon_password == addon_password

        # Test manifest endpoint with valid secret_str
        response = client.get(f"/{secret_str}/manifest.json")
        assert response.status_code == 200
        manifest = response.json()
        assert manifest["id"] == "org.stremio.eyepeateavea"

        response = client.get(f"/invalid_secret/manifest.json")
        assert response.status_code == 404

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
        redis_store_fixture.store_channels([sample_channel])

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
