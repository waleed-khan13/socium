from __future__ import annotations

import ctypes
import os
import shutil
import time
from pathlib import Path
from typing import Any

from app.config import Settings, get_settings

LOW_SPACE_BYTES = 2 * 1024 * 1024 * 1024
STORAGE_CACHE_SECONDS = 60.0
_cache: tuple[float, tuple[str, str, str], dict[str, Any]] | None = None


def _directory_bytes(directory: Path, *, excluded_names: frozenset[str] = frozenset()) -> int:
    if not directory.exists():
        return 0
    total = 0
    try:
        for root, directories, files in os.walk(directory):
            directories[:] = [name for name in directories if name not in excluded_names]
            for filename in files:
                try:
                    total += (Path(root) / filename).stat().st_size
                except OSError:
                    continue
    except OSError:
        return 0
    return total


def _file_group_bytes(directory: Path, names: set[str]) -> int:
    total = 0
    for name in names:
        try:
            total += (directory / name).stat().st_size
        except OSError:
            continue
    return total


def _location_kind(location: Path) -> str:
    value = str(location).casefold()
    if value.startswith("\\\\"):
        return "network"
    if any(part in value for part in ("onedrive", "dropbox", "google drive", "icloud")):
        return "cloud-synced"
    if os.name == "nt" and location.drive:
        try:
            drive_type = ctypes.windll.kernel32.GetDriveTypeW(f"{location.drive}\\")
            if drive_type == 2:
                return "removable"
            if drive_type == 4:
                return "network"
        except (AttributeError, OSError):
            pass
    return "local"


def _volume_state(location: Path) -> dict[str, Any]:
    try:
        usage = shutil.disk_usage(location)
        threshold = max(LOW_SPACE_BYTES, int(usage.total * 0.05))
        return {
            "available": True,
            "totalBytes": usage.total,
            "freeBytes": usage.free,
            "lowSpace": usage.free < threshold,
        }
    except OSError:
        return {"available": False, "totalBytes": 0, "freeBytes": 0, "lowSpace": True}


def _build_storage_state(settings: Settings) -> dict[str, Any]:
    data_dir = settings.data_dir
    categories = {
        "database": _file_group_bytes(data_dir, {"socium.db", "socium.db-wal", "socium.db-shm"}),
        "credentials": _file_group_bytes(data_dir, {"master.key"}),
        "media": _directory_bytes(data_dir / "media"),
        "logs": _directory_bytes(data_dir / "logs"),
        "exports": _directory_bytes(data_dir / "exports"),
        "backups": _directory_bytes(data_dir / "backups"),
    }
    data_bytes = _directory_bytes(data_dir)
    categories["other"] = max(0, data_bytes - sum(categories.values()))
    locations = {
        "runtime": {"path": str(settings.runtime_dir), "kind": _location_kind(settings.runtime_dir)},
        "data": {"path": str(data_dir), "kind": _location_kind(data_dir)},
        "models": {"path": str(settings.models_dir), "kind": _location_kind(settings.models_dir)},
    }
    data_volume = _volume_state(data_dir)
    models_volume = _volume_state(settings.models_dir)
    warnings: list[str] = []
    if not data_volume["available"]:
        warnings.append("Data drive unavailable")
    elif data_volume["lowSpace"]:
        warnings.append("Durable data drive is low on free space.")
    if not models_volume["available"]:
        warnings.append("Local AI model drive unavailable")
    elif models_volume["lowSpace"]:
        warnings.append("Local AI model drive is low on free space.")
    for label in ("data", "models"):
        kind = locations[label]["kind"]
        if kind != "local":
            warnings.append(
                f"The {label} location is {kind}; a local fixed drive is safer and more reliable."
            )
    return {
        "locations": locations,
        "usage": {
            "runtimeBytes": _directory_bytes(
                settings.runtime_dir,
                excluded_names=frozenset(
                    {".git", ".next", ".venv", "node_modules", "output", "release"}
                ),
            ),
            "dataBytes": data_bytes,
            "modelsBytes": _directory_bytes(settings.models_dir),
            "categories": categories,
        },
        "volumes": {"data": data_volume, "models": models_volume},
        "warnings": warnings,
        "healthy": not warnings,
        "moveCommand": "socium storage move --data-dir <path> --models-dir <path>",
        "sourcePreservation": "Previous storage is preserved until you confirm the new location works.",
    }


def storage_state(settings: Settings | None = None, *, refresh: bool = False) -> dict[str, Any]:
    global _cache
    now = time.monotonic()
    resolved_settings = settings or get_settings()
    location_key = (
        str(resolved_settings.runtime_dir),
        str(resolved_settings.data_dir),
        str(resolved_settings.models_dir),
    )
    if (
        not refresh
        and _cache
        and _cache[1] == location_key
        and now - _cache[0] < STORAGE_CACHE_SECONDS
    ):
        return _cache[2]
    result = _build_storage_state(resolved_settings)
    _cache = (now, location_key, result)
    return result
