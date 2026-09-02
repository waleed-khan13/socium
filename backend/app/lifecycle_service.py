from __future__ import annotations

import asyncio
import hashlib
import json
import os
import platform
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app import __version__
from app.database import read_session, write_session
from app.errors import AppError
from app.models import AppMetadata

DEFAULT_MANIFEST = "https://github.com/waleed-khan13/socium/releases/latest/download/socium-manifest.json"
CHECK_INTERVAL = timedelta(hours=24)
MAX_UPDATE_BYTES = 8 * 1024 * 1024 * 1024


def _metadata(key: str) -> str | None:
    with read_session() as session:
        row = session.get(AppMetadata, key)
        return row.value if row else None


def _set_metadata(key: str, value: str) -> None:
    with write_session() as session:
        row = session.get(AppMetadata, key)
        if row is None:
            session.add(AppMetadata(key=key, value=value))
        else:
            row.value = value


def _parts(value: str) -> tuple[int, int, int]:
    clean = value.split("-", 1)[0].split("+", 1)[0]
    try:
        major, minor, patch = clean.split(".")
        return int(major), int(minor), int(patch)
    except (TypeError, ValueError) as error:
        raise AppError("The release server returned an invalid version.", status_code=502) from error


def _manifest_url() -> str:
    value = os.getenv("SOCIUM_RELEASE_MANIFEST", "").strip() or DEFAULT_MANIFEST
    if not value.startswith("https://") and os.getenv("SOCIUM_ALLOW_INSECURE_DOWNLOADS") != "1":
        raise AppError("The update manifest must use HTTPS.", status_code=503)
    return value


def _cached_state() -> dict[str, Any]:
    raw = _metadata("lifecycle_update_state")
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except (ValueError, TypeError):
            pass
    return {
        "currentVersion": os.getenv("SOCIUM_APP_VERSION", __version__),
        "latestVersion": None,
        "updateAvailable": False,
        "releaseNotes": "",
        "releaseNotesUrl": None,
        "publishedAt": None,
        "checkedAt": None,
        "status": "idle",
        "lastError": None,
    }


def lifecycle_state() -> dict[str, Any]:
    state = _cached_state()
    state["managedRuntime"] = bool(os.getenv("SOCIUM_CONTROL_URL") and os.getenv("SOCIUM_CONTROL_TOKEN"))
    state["automaticChecks"] = os.getenv("SOCIUM_AUTO_UPDATE_CHECKS", "1").strip().lower() not in {"0", "false", "no", "off"}
    state["rollbackAvailable"] = False
    runtime_dir = os.getenv("SOCIUM_RUNTIME_DIR", "").strip()
    if runtime_dir:
        try:
            installation = json.loads((Path(runtime_dir).parents[2] / "installation.json").read_text(encoding="utf-8"))
            state["rollbackAvailable"] = bool((installation.get("previousRelease") or {}).get("runtimePath"))
        except (OSError, ValueError, IndexError):
            pass
    return state


def check_for_updates(*, force: bool = False) -> dict[str, Any]:
    current = _cached_state()
    if not force and current.get("checkedAt"):
        checked_at = datetime.fromisoformat(current["checkedAt"])
        if datetime.now(UTC) - checked_at < CHECK_INTERVAL:
            return lifecycle_state()
    request = urllib.request.Request(
        _manifest_url(),
        headers={
            "User-Agent": f"Socium/{__version__} ({platform.system()}; {platform.machine()})",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            if not response.geturl().startswith("https://"):
                raise AppError("The update server redirected to an insecure address.", status_code=502)
            manifest = json.loads(response.read(1024 * 1024).decode("utf-8"))
        if manifest.get("product") != "socium" or manifest.get("schemaVersion") != 1:
            raise AppError("The update server returned an invalid Socium manifest.", status_code=502)
        latest = str(manifest.get("version") or "")
        release_notes_url = str(manifest.get("releaseNotesUrl") or "")[:2_048]
        result = {
            "currentVersion": os.getenv("SOCIUM_APP_VERSION", __version__),
            "latestVersion": latest,
            "updateAvailable": _parts(os.getenv("SOCIUM_APP_VERSION", __version__)) < _parts(latest),
            "releaseNotes": str(manifest.get("releaseNotes") or "")[:20_000],
            "releaseNotesUrl": release_notes_url if release_notes_url.startswith("https://") else None,
            "publishedAt": manifest.get("publishedAt"),
            "checkedAt": datetime.now(UTC).isoformat(),
            "status": "ready",
            "lastError": None,
        }
    except AppError as error:
        result = {**current, "checkedAt": datetime.now(UTC).isoformat(), "status": "error", "lastError": error.message}
        _set_metadata("lifecycle_update_state", json.dumps(result))
        if force:
            raise
        return lifecycle_state()
    except (OSError, ValueError, urllib.error.URLError, json.JSONDecodeError) as error:
        result = {**current, "checkedAt": datetime.now(UTC).isoformat(), "status": "error", "lastError": str(error)[:500]}
        _set_metadata("lifecycle_update_state", json.dumps(result))
        if force:
            raise AppError(f"Could not check for updates: {error}", status_code=502) from error
        return lifecycle_state()
    _set_metadata("lifecycle_update_state", json.dumps(result))
    return lifecycle_state()


def _release_target() -> str:
    configured = os.getenv("SOCIUM_RELEASE_TARGET", "").strip()
    if configured:
        return configured
    system = "win32" if sys.platform == "win32" else "darwin" if sys.platform == "darwin" else "linux"
    machine = platform.machine().casefold()
    architecture = "arm64" if machine in {"arm64", "aarch64"} else "x64"
    return f"{system}-{architecture}"


def prepare_update_stream():
    partial: Path | None = None
    request = urllib.request.Request(
        _manifest_url(),
        headers={
            "User-Agent": f"Socium/{__version__} ({platform.system()}; {platform.machine()})",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            if not response.geturl().startswith("https://"):
                raise AppError("The update server redirected to an insecure address.", status_code=502)
            manifest = json.loads(response.read(1024 * 1024).decode("utf-8"))
        latest = str(manifest.get("version") or "")
        current = os.getenv("SOCIUM_APP_VERSION", __version__)
        if _parts(latest) <= _parts(current):
            raise AppError("No newer Socium release is available.", status_code=409)
        target = _release_target()
        asset = (manifest.get("assets") or {}).get(target) or {}
        source = str(asset.get("url") or "")
        expected = str(asset.get("sha256") or "").casefold()
        if (
            manifest.get("product") != "socium"
            or manifest.get("schemaVersion") != 1
            or not source.startswith("https://")
            or len(expected) != 64
            or any(character not in "0123456789abcdef" for character in expected)
        ):
            raise AppError("The release manifest has no trusted bundle for this computer.", status_code=502)
        runtime_value = os.getenv("SOCIUM_RUNTIME_DIR", "").strip()
        if not runtime_value:
            raise AppError("Updates can be prepared only in the installed Socium runtime.", status_code=409)
        data_value = os.getenv("SOCIUM_DATA_DIR", "").strip()
        if not data_value:
            raise AppError("The durable data location is unavailable.", status_code=409)
        data_dir = Path(data_value)
        update_dir = data_dir / ".updates"
        update_dir.mkdir(parents=True, exist_ok=True)
        partial = update_dir / "bundle.tar.gz.partial"
        archive = update_dir / "bundle.tar.gz"
        prepared_manifest = update_dir / "prepared-manifest.json"
        checksum = hashlib.sha256()
        downloaded = 0
        last_percentage = -1
        asset_request = urllib.request.Request(source, headers={"User-Agent": f"Socium/{__version__}"})
        with urllib.request.urlopen(asset_request, timeout=60) as response, partial.open("wb") as output:
            if not response.geturl().startswith("https://"):
                raise AppError("The release server redirected to an insecure address.", status_code=502)
            total = int(response.headers.get("Content-Length") or 0)
            if total > MAX_UPDATE_BYTES:
                raise AppError("The release bundle is larger than Socium's safety limit.", status_code=502)
            yield json.dumps({"status": "downloading", "downloadedBytes": 0, "totalBytes": total, "percentage": 0}) + "\n"
            last_percentage = 0
            while block := response.read(1024 * 1024):
                output.write(block)
                checksum.update(block)
                downloaded += len(block)
                if downloaded > MAX_UPDATE_BYTES:
                    raise AppError("The release bundle exceeded Socium's safety limit.", status_code=502)
                percentage = min(100, int(downloaded * 100 / total)) if total else None
                if percentage is None:
                    yield json.dumps({"status": "downloading", "downloadedBytes": downloaded, "totalBytes": None, "percentage": None}) + "\n"
                elif percentage > last_percentage:
                    for crossed in range(last_percentage + 1, percentage + 1):
                        yield json.dumps({"status": "downloading", "downloadedBytes": downloaded, "totalBytes": total, "percentage": crossed}) + "\n"
                    last_percentage = percentage
        if checksum.hexdigest() != expected:
            partial.unlink(missing_ok=True)
            raise AppError("Release bundle checksum verification failed.", status_code=502)
        partial.replace(archive)
        local_manifest = {
            "schemaVersion": 1,
            "product": "socium",
            "version": manifest.get("version"),
            "publishedAt": manifest.get("publishedAt"),
            "releaseNotes": manifest.get("releaseNotes", ""),
            "releaseNotesUrl": manifest.get("releaseNotesUrl"),
            "assets": {target: {"url": archive.name, "sha256": expected}},
        }
        prepared_manifest.write_text(json.dumps(local_manifest, indent=2), encoding="utf-8")
        yield json.dumps({"status": "ready", "downloadedBytes": downloaded, "totalBytes": downloaded, "percentage": 100}) + "\n"
    except AppError as error:
        if partial is not None:
            partial.unlink(missing_ok=True)
        yield json.dumps({"status": "error", "error": error.message}) + "\n"
    except (OSError, ValueError, urllib.error.URLError, json.JSONDecodeError) as error:
        if partial is not None:
            partial.unlink(missing_ok=True)
        yield json.dumps({"status": "error", "error": f"Could not prepare update: {error}"}) + "\n"


def runtime_controller_available() -> bool:
    base_url = os.getenv("SOCIUM_CONTROL_URL", "").strip()
    token = os.getenv("SOCIUM_CONTROL_TOKEN", "").strip()
    return bool(base_url and token and base_url.startswith("http://127.0.0.1:"))


def request_controller_action(action: str) -> dict[str, Any]:
    if action not in {"stop", "restart", "update", "rollback"}:
        raise AppError("Unsupported runtime action.")
    base_url = os.getenv("SOCIUM_CONTROL_URL", "").strip()
    token = os.getenv("SOCIUM_CONTROL_TOKEN", "").strip()
    if not base_url or not token:
        raise AppError("This action is available in the installed Socium runtime.", status_code=409)
    if not base_url.startswith("http://127.0.0.1:"):
        raise AppError("The local runtime controller address is invalid.", status_code=503)
    request = urllib.request.Request(
        f"{base_url}/{action}",
        data=b"{}",
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, ValueError) as error:
        raise AppError(f"The local runtime controller did not accept the request: {error}", status_code=503) from error


def request_storage_move(data_directory: str, models_directory: str) -> dict[str, Any]:
    base_url = os.getenv("SOCIUM_CONTROL_URL", "").strip()
    token = os.getenv("SOCIUM_CONTROL_TOKEN", "").strip()
    if not base_url or not token:
        raise AppError(
            "Automatic storage moving is available in the installed Socium app. "
            "Restart the installed app, then choose the folders again.",
            status_code=409,
        )
    if not base_url.startswith("http://127.0.0.1:"):
        raise AppError("The local runtime controller address is invalid.", status_code=503)
    body = json.dumps(
        {"dataDir": data_directory, "modelsDir": models_directory}
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}/storage-move",
        data=body,
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, ValueError) as error:
        raise AppError(
            f"The local runtime controller did not accept the storage move: {error}",
            status_code=503,
        ) from error


class UpdateMonitor:
    def __init__(self, idle_check: Callable[[], bool] | None = None) -> None:
        self._task: asyncio.Task[None] | None = None
        self._idle_check = idle_check or (lambda: True)

    def start(self) -> None:
        if not lifecycle_state()["automaticChecks"]:
            return
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="daily-update-check")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(10)
            if not self._idle_check():
                await asyncio.sleep(60)
                continue
            await asyncio.to_thread(check_for_updates)
            state = _cached_state()
            try:
                checked = datetime.fromisoformat(state["checkedAt"]) if state.get("checkedAt") else datetime.now(UTC)
            except (TypeError, ValueError):
                checked = datetime.now(UTC)
            delay = max(60.0, (checked + CHECK_INTERVAL - datetime.now(UTC)).total_seconds())
            await asyncio.sleep(delay)
