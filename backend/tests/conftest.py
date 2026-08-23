from __future__ import annotations

import os

import pytest


@pytest.fixture(scope="session")
def client(tmp_path_factory: pytest.TempPathFactory):
    data_dir = tmp_path_factory.mktemp("socium-data")
    os.environ["SOCIUM_DATA_DIR"] = str(data_dir)
    os.environ["SOCIUM_MODELS_DIR"] = str(data_dir.parent / "socium-models")
    os.environ["SOCIUM_TELEGRAM_POLL_TIMEOUT"] = "5"
    os.environ["SOCIUM_SCHEDULER_INTERVAL"] = "0.1"
    os.environ["SOCIUM_SLACK_SOCKET_MODE"] = "0"
    os.environ["SOCIUM_ENABLE_LABS"] = "0"
    os.environ["SOCIUM_AUTO_UPDATE_CHECKS"] = "0"

    from app.config import get_settings

    get_settings.cache_clear()
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
