from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic.config import Config

from alembic import command


def _alembic_config(database_path: Path) -> Config:
    backend_root = Path(__file__).resolve().parents[1]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    return config


def test_v1_1_migration_removes_only_legacy_whatsapp_credentials(tmp_path: Path) -> None:
    database_path = tmp_path / "socium.db"
    config = _alembic_config(database_path)
    command.upgrade(config, "20260810_0012")

    account_values = (
        "{}",
        "encrypted-local-secret",
        "[]",
        1,
        "verified",
        None,
        None,
        None,
        "2026-08-23T00:00:00Z",
        "2026-08-23T00:00:00Z",
    )
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO connector_accounts (
                id, adapter_id, name, config, encrypted_secrets, scopes, enabled,
                status, remote_account_id, last_verified_at, last_error, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("legacy-whatsapp", "whatsapp", "Legacy review", *account_values),
        )
        connection.execute(
            """
            INSERT INTO connector_accounts (
                id, adapter_id, name, config, encrypted_secrets, scopes, enabled,
                status, remote_account_id, last_verified_at, last_error, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("keep-slack", "slack", "Slack approvals", *account_values),
        )

    command.upgrade(config, "head")

    with sqlite3.connect(database_path) as connection:
        accounts = connection.execute(
            "SELECT id, adapter_id, encrypted_secrets FROM connector_accounts ORDER BY id"
        ).fetchall()
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()

    assert accounts == [("keep-slack", "slack", "encrypted-local-secret")]
    assert revision == ("20260823_0013",)
