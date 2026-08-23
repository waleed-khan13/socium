from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    project_root: Path
    data_dir: Path
    database_path: Path
    master_key_path: Path
    legacy_json_path: Path
    models_dir: Path
    runtime_dir: Path
    storage_marker_required: bool
    host: str
    port: int
    telegram_poll_timeout: int
    scheduler_interval: float
    scheduler_catch_up_hours: int
    scheduler_stale_minutes: int
    scheduler_lease_seconds: int
    scheduler_worker_timeout_seconds: int
    scheduler_crash_limit: int
    slack_socket_enabled: bool
    labs_enabled: bool
    migration_check: bool

    @property
    def database_url(self) -> str:
        return f"sqlite+pysqlite:///{self.database_path.resolve().as_posix()}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    backend_root = Path(__file__).resolve().parents[1]
    project_root = backend_root.parent
    configured_data_dir = os.getenv("SOCIUM_DATA_DIR", "").strip()
    data_dir = (
        Path(configured_data_dir).expanduser().resolve() if configured_data_dir else project_root / "data"
    )
    configured_models_dir = os.getenv("SOCIUM_MODELS_DIR", "").strip()
    models_dir = (
        Path(configured_models_dir).expanduser().resolve()
        if configured_models_dir
        else project_root / "models"
    )
    configured_runtime_dir = os.getenv("SOCIUM_RUNTIME_DIR", "").strip()
    runtime_dir = (
        Path(configured_runtime_dir).expanduser().resolve() if configured_runtime_dir else project_root
    )
    storage_marker_required = os.getenv("SOCIUM_STORAGE_REQUIRE_MARKER", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    host = os.getenv("SOCIUM_API_HOST", "127.0.0.1").strip() or "127.0.0.1"
    port = int(os.getenv("SOCIUM_API_PORT", "8000"))
    poll_timeout = max(5, min(int(os.getenv("SOCIUM_TELEGRAM_POLL_TIMEOUT", "25")), 50))
    scheduler_interval = max(0.1, min(float(os.getenv("SOCIUM_SCHEDULER_INTERVAL", "1")), 10))
    scheduler_catch_up_hours = max(1, min(int(os.getenv("SOCIUM_SCHEDULER_CATCH_UP_HOURS", "24")), 168))
    scheduler_stale_minutes = max(1, min(int(os.getenv("SOCIUM_SCHEDULER_STALE_MINUTES", "10")), 60))
    scheduler_worker_timeout_seconds = max(
        5,
        min(int(os.getenv("SOCIUM_WORKER_TIMEOUT_SECONDS", "300")), 3_600),
    )
    scheduler_lease_seconds = max(
        scheduler_worker_timeout_seconds + 30,
        min(int(os.getenv("SOCIUM_WORKER_LEASE_SECONDS", "360")), 7_200),
    )
    scheduler_crash_limit = max(1, min(int(os.getenv("SOCIUM_SUPERVISOR_CRASH_LIMIT", "3")), 10))
    slack_socket_enabled = os.getenv("SOCIUM_SLACK_SOCKET_MODE", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }
    labs_enabled = os.getenv("SOCIUM_ENABLE_LABS", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    migration_check = os.getenv("SOCIUM_MIGRATION_CHECK", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    return Settings(
        project_root=project_root,
        data_dir=data_dir,
        database_path=data_dir / "socium.db",
        master_key_path=data_dir / "master.key",
        legacy_json_path=data_dir / "socium.json",
        models_dir=models_dir,
        runtime_dir=runtime_dir,
        storage_marker_required=storage_marker_required,
        host=host,
        port=port,
        telegram_poll_timeout=poll_timeout,
        scheduler_interval=scheduler_interval,
        scheduler_catch_up_hours=scheduler_catch_up_hours,
        scheduler_stale_minutes=scheduler_stale_minutes,
        scheduler_lease_seconds=scheduler_lease_seconds,
        scheduler_worker_timeout_seconds=scheduler_worker_timeout_seconds,
        scheduler_crash_limit=scheduler_crash_limit,
        slack_socket_enabled=slack_socket_enabled,
        labs_enabled=labs_enabled,
        migration_check=migration_check,
    )
