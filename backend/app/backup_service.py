from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import tarfile
import tempfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.errors import AppError


def _digest(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


def list_backups() -> list[dict[str, Any]]:
    backup_dir = get_settings().data_dir / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    items = []
    for archive in backup_dir.glob("socium-backup-*.tar.gz"):
        info = archive.stat()
        checksum_path = Path(f"{archive}.sha256")
        try:
            checksum = checksum_path.read_text(encoding="utf-8").split()[0]
        except (OSError, IndexError):
            checksum = ""
        items.append(
            {
                "name": archive.name,
                "path": str(archive),
                "sizeBytes": info.st_size,
                "createdAt": datetime.fromtimestamp(info.st_mtime, UTC).isoformat(),
                "checksum": checksum,
            }
        )
    return sorted(items, key=lambda item: item["createdAt"], reverse=True)


def create_backup(*, reason: str = "manual") -> dict[str, Any]:
    settings = get_settings()
    backup_dir = settings.data_dir / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC)
    filename = f"socium-backup-{now.strftime('%Y-%m-%dT%H-%M-%S-%fZ')}.tar.gz"
    destination = backup_dir / filename
    with tempfile.TemporaryDirectory(prefix="socium-backup-") as temporary:
        staging = Path(temporary)
        for source in settings.data_dir.rglob("*"):
            relative = source.relative_to(settings.data_dir)
            if not relative.parts or relative.parts[0] in {"backups", ".updates"}:
                continue
            if source.is_symlink():
                raise AppError("A symbolic link in the data directory prevented a safe backup.")
            if source.name in {"socium.db", "socium.db-wal", "socium.db-shm", ".socium-runtime.json"}:
                continue
            target = staging / relative
            if source.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            elif source.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        database_copy = staging / "socium.db"
        with (
            closing(sqlite3.connect(settings.database_path)) as source_db,
            closing(sqlite3.connect(database_copy)) as target_db,
        ):
            source_db.backup(target_db)
        metadata = {
            "schemaVersion": 1,
            "product": "socium",
            "createdAt": now.isoformat(),
            "appVersion": __import__("app").__version__,
            "reason": reason,
        }
        (staging / ".socium-backup.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        with tarfile.open(destination, "w:gz") as archive:
            for item in staging.iterdir():
                archive.add(item, arcname=item.name, recursive=True)
    checksum = _digest(destination)
    destination.with_suffix(destination.suffix + ".sha256").write_text(
        f"{checksum}  {filename}\n", encoding="utf-8"
    )
    return {"name": filename, "path": str(destination), "sizeBytes": destination.stat().st_size, "checksum": checksum, **metadata}
