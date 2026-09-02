from __future__ import annotations

import atexit
import os
import shutil
import tempfile
from pathlib import Path

import pytest

_TEST_ROOT = Path(tempfile.mkdtemp(prefix="socium-pytest-"))
_TEST_DATA_DIR = _TEST_ROOT / "data"
_TEST_MODELS_DIR = _TEST_ROOT / "models"
_TEST_DATA_DIR.mkdir(parents=True)
_TEST_MODELS_DIR.mkdir(parents=True)
atexit.register(shutil.rmtree, _TEST_ROOT, ignore_errors=True)

# Set isolation before pytest imports any test module. A test that imports app code
# during collection must never initialize Socium against a user's real local database.
os.environ["SOCIUM_DATA_DIR"] = str(_TEST_DATA_DIR)
os.environ["SOCIUM_MODELS_DIR"] = str(_TEST_MODELS_DIR)
os.environ["SOCIUM_TELEGRAM_POLL_TIMEOUT"] = "5"
os.environ["SOCIUM_SCHEDULER_INTERVAL"] = "0.1"
os.environ["SOCIUM_SLACK_SOCKET_MODE"] = "0"
os.environ["SOCIUM_ENABLE_LABS"] = "0"
os.environ["SOCIUM_AUTO_UPDATE_CHECKS"] = "0"


@pytest.fixture(autouse=True)
def stub_post_package_images(monkeypatch):
    """Keep existing content-flow tests deterministic and free of paid image calls."""
    from app import main as app_main
    from app.services import provider as provider_service
    from app.services.content_package import GeneratedPostPackage

    async def fake_package(provider, request, workspace):
        content = await provider_service.generate_content(provider, request, workspace)
        return GeneratedPostPackage(
            content=content,
            media_asset_id="",
            image_provider_kind="test-images",
            image_model="test-image-model",
        )

    monkeypatch.setattr(app_main, "generate_post_package", fake_package)


@pytest.fixture(scope="session")
def client():
    from app.config import get_settings

    get_settings.cache_clear()
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
