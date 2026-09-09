from __future__ import annotations

import asyncio
import json

import pytest

from app import lifecycle_service as lifecycle
from app.errors import AppError


@pytest.fixture(autouse=True)
def update_state(client, monkeypatch):
    keys = ("lifecycle_update_state", "lifecycle_automatic_install",
            "lifecycle_automatic_attempt", "lifecycle_automatic_error")
    previous = {key: lifecycle._metadata(key) for key in keys}
    for key in keys:
        lifecycle._set_metadata(key, "")
    monkeypatch.setattr(lifecycle, "_automatic_progress", None)
    monkeypatch.setenv("SOCIUM_APP_VERSION", "1.4.0")
    monkeypatch.setenv("SOCIUM_CONTROL_URL", "http://127.0.0.1:45678")
    monkeypatch.setenv("SOCIUM_CONTROL_TOKEN", "test-controller-only")
    monkeypatch.setenv("SOCIUM_AUTO_UPDATE_CHECKS", "1")
    yield
    for key, value in previous.items():
        lifecycle._set_metadata(key, value or "")


def available_update(monkeypatch):
    lifecycle._set_metadata("lifecycle_update_state", json.dumps({
        "currentVersion": "1.4.0", "latestVersion": "1.4.1",
        "status": "ready", "checkedAt": "2026-09-08T00:00:00+00:00",
    }))
    lifecycle.save_update_preferences(True)
    monkeypatch.setattr(lifecycle, "check_for_updates", lambda: lifecycle.lifecycle_state())


def test_preferences_are_opt_in_persistent_and_can_be_disabled(client):
    assert client.get("/api/lifecycle").json()["lifecycle"]["automaticInstall"] is False
    response = client.put("/api/lifecycle/preferences", json={"automaticInstall": True})
    assert response.status_code == 200
    assert client.get("/api/lifecycle").json()["lifecycle"]["automaticInstall"] is True
    response = client.put("/api/lifecycle/preferences", json={"automaticInstall": False})
    assert response.json()["lifecycle"]["automaticInstall"] is False
    assert response.json()["lifecycle"]["automaticChecks"] is True


def test_preferences_require_managed_runtime_and_checks(client, monkeypatch):
    monkeypatch.delenv("SOCIUM_CONTROL_TOKEN")
    assert client.put("/api/lifecycle/preferences", json={"automaticInstall": True}).status_code == 409
    monkeypatch.setenv("SOCIUM_CONTROL_TOKEN", "test")
    monkeypatch.setenv("SOCIUM_AUTO_UPDATE_CHECKS", "0")
    assert client.put("/api/lifecycle/preferences", json={"automaticInstall": True}).status_code == 409
    assert client.put("/api/lifecycle/preferences", json={}).status_code == 422


def test_installed_version_is_not_taken_from_old_cache(monkeypatch):
    available_update(monkeypatch)
    monkeypatch.setenv("SOCIUM_APP_VERSION", "1.4.1")
    state = lifecycle.lifecycle_state()
    assert state["currentVersion"] == "1.4.1"
    assert state["updateAvailable"] is False


def test_auto_install_once_and_never_during_active_work(monkeypatch):
    available_update(monkeypatch)
    calls = []
    idle = False

    def prepare():
        calls.append("prepare")
        yield json.dumps({"status": "ready", "percentage": 100})

    async def install():
        calls.append("install")
        return True

    monkeypatch.setattr(lifecycle, "prepare_update_stream", prepare)
    monitor = lifecycle.UpdateMonitor(lambda: idle, install)
    asyncio.run(monitor.tick())
    assert calls == []
    idle = True
    asyncio.run(monitor.tick())
    asyncio.run(monitor.tick())
    asyncio.run(lifecycle.UpdateMonitor(lambda: True, install).tick())
    assert calls == ["prepare", "install"]


@pytest.mark.parametrize("disable", [False, True])
def test_rechecks_work_and_consent_after_download(monkeypatch, disable):
    available_update(monkeypatch)
    idle = True
    installs = []

    def prepare():
        nonlocal idle
        if disable:
            lifecycle.save_update_preferences(False)
        else:
            idle = False
        yield json.dumps({"status": "ready", "percentage": 100})

    async def install():
        installs.append(True)
        return True

    monkeypatch.setattr(lifecycle, "prepare_update_stream", prepare)
    monitor = lifecycle.UpdateMonitor(lambda: idle, install)
    asyncio.run(monitor.tick())
    assert installs == []
    if not disable:
        idle = True
        asyncio.run(monitor.tick())
        assert installs == [True]


def test_failed_download_is_not_retried_or_leaked(monkeypatch):
    available_update(monkeypatch)
    calls = []

    def prepare():
        calls.append(True)
        yield json.dumps({"status": "error", "error": "private-server-token"})

    async def install():
        pytest.fail("Failed downloads must not install")

    monkeypatch.setattr(lifecycle, "prepare_update_stream", prepare)
    for _ in range(2):
        asyncio.run(lifecycle.UpdateMonitor(lambda: True, install).tick())
    assert calls == [True]
    assert "private-server-token" not in json.dumps(lifecycle.lifecycle_state())
    assert "Use Update now" in lifecycle.lifecycle_state()["automaticError"]


def test_controller_failure_does_not_restart_loop(monkeypatch):
    available_update(monkeypatch)
    monkeypatch.setattr(lifecycle, "prepare_update_stream", lambda: iter([json.dumps({"status": "ready"})]))
    attempts = []

    async def install():
        attempts.append(True)
        raise AppError("controller unavailable")

    monitor = lifecycle.UpdateMonitor(lambda: True, install)
    asyncio.run(monitor.tick())
    asyncio.run(monitor.tick())
    assert attempts == [True]
    assert lifecycle.lifecycle_state()["automaticError"]


def test_concurrent_download_is_refused():
    with lifecycle._prepare_lock:
        events = [json.loads(line) for line in lifecycle.prepare_update_stream()]
    assert events[0]["status"] == "error"
    assert "already in progress" in events[0]["error"]


def test_automatic_handover_restores_scheduler_on_controller_failure(monkeypatch):
    from app import main

    lifecycle.save_update_preferences(True)
    calls = []

    class Scheduler:
        def status(self):
            return {"workersActive": 0}

        async def stop(self):
            calls.append("stop")

        def start(self):
            calls.append("start")

    def controller(_action):
        calls.append("controller")
        raise AppError("helper unavailable")

    monkeypatch.setattr(main, "local_scheduler", Scheduler())
    monkeypatch.setattr(main, "request_controller_action", controller)
    with pytest.raises(AppError):
        asyncio.run(main.install_automatic_update())
    assert calls == ["stop", "controller", "start"]


def test_automatic_handover_never_stops_an_active_worker(monkeypatch):
    from app import main

    class Scheduler:
        def status(self):
            return {"workersActive": 1}

        async def stop(self):
            pytest.fail("An active worker must not be stopped for an update")

    monkeypatch.setattr(main, "local_scheduler", Scheduler())
    assert asyncio.run(main.install_automatic_update()) is False
