from __future__ import annotations

import errno
import hashlib
import json
import platform
import sqlite3
import tarfile
from pathlib import Path


def test_online_backup_is_consistent_and_listed(client, tmp_path: Path) -> None:
    from app.config import get_settings

    settings = get_settings()
    marker = settings.data_dir / ".socium-storage.json"
    marker.write_text(json.dumps({"schemaVersion": 1, "product": "socium"}), encoding="utf-8")
    response = client.post("/api/lifecycle/backup")
    assert response.status_code == 200
    backup = response.json()["backup"]
    archive_path = Path(backup["path"])
    assert archive_path.is_file()
    assert Path(f"{archive_path}.sha256").is_file()
    with tarfile.open(archive_path, "r:gz") as archive:
        names = archive.getnames()
        database_member = archive.extractfile("socium.db")
        assert database_member is not None
        restored_database = tmp_path / "restored-socium.db"
        restored_database.write_bytes(database_member.read())
    assert "socium.db" in names
    assert ".socium-backup.json" in names
    assert not any(name.startswith("backups/") for name in names)
    connection = sqlite3.connect(restored_database)
    try:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'workspace'").fetchone() == ("workspace",)
    finally:
        connection.close()
    assert client.get("/api/lifecycle").json()["backups"][0]["checksum"] == backup["checksum"]


def test_full_data_drive_leaves_no_incomplete_backup(client, monkeypatch) -> None:
    from app.config import get_settings

    backup_dir = get_settings().data_dir / "backups"
    before = set(backup_dir.glob("socium-backup-*"))

    def fail_archive(*_args, **_kwargs):
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr("app.backup_service.tarfile.open", fail_archive)
    response = client.post("/api/lifecycle/backup")
    assert response.status_code == 507
    assert "data drive is full" in response.json()["error"]
    assert set(backup_dir.glob("socium-backup-*")) == before
    assert not list(backup_dir.glob("*.partial"))


def test_manual_update_check_uses_minimal_platform_metadata(client, monkeypatch) -> None:
    captured: dict[str, object] = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def geturl(self):
            return "https://updates.example/socium-manifest.json"

        def read(self, _limit):
            return json.dumps(
                {
                    "schemaVersion": 1,
                    "product": "socium",
                    "version": "1.1.0",
                    "publishedAt": "2026-08-24T00:00:00Z",
                    "releaseNotes": "Native lifecycle controls.",
                }
            ).encode()

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = {key.lower(): value for key, value in request.header_items()}
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setenv("SOCIUM_RELEASE_MANIFEST", "https://updates.example/socium-manifest.json")
    monkeypatch.setenv("SOCIUM_APP_VERSION", "1.0.5")
    monkeypatch.setattr("app.lifecycle_service.urllib.request.urlopen", fake_urlopen)
    response = client.post("/api/lifecycle/check")
    assert response.status_code == 200
    lifecycle = response.json()["lifecycle"]
    assert lifecycle["updateAvailable"] is True
    assert lifecycle["latestVersion"] == "1.1.0"
    assert captured["url"] == "https://updates.example/socium-manifest.json"
    assert captured["headers"] == {
        "accept": "application/json",
        "user-agent": f"Socium/1.1.0 ({platform.system()}; {platform.machine()})",
    }
    assert captured["timeout"] == 15


def test_runtime_actions_are_refused_outside_managed_install(client) -> None:
    response = client.post("/api/lifecycle/update")
    assert response.status_code == 409
    assert "installed Socium runtime" in response.json()["error"]


def test_update_prepare_stream_reports_every_percentage_and_verifies_checksum(client, monkeypatch) -> None:
    from app.config import get_settings
    from app.lifecycle_service import prepare_update_stream

    payload = b"x" * 100
    checksum = hashlib.sha256(payload).hexdigest()

    class Response:
        def __init__(self, *, body: bytes, url: str, content_length: int | None = None):
            self.body = body
            self.url = url
            self.offset = 0
            self.headers = {"Content-Length": str(content_length)} if content_length else {}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def geturl(self):
            return self.url

        def read(self, limit):
            chunk = self.body[self.offset : self.offset + limit]
            self.offset += len(chunk)
            return chunk

    manifest = json.dumps(
        {
            "schemaVersion": 1,
            "product": "socium",
            "version": "1.1.0",
            "assets": {"win32-x64": {"url": "https://updates.example/bundle.tar.gz", "sha256": checksum}},
        }
    ).encode()

    def fake_urlopen(request, timeout):
        if request.full_url.endswith("manifest.json"):
            return Response(body=manifest, url=request.full_url)
        assert timeout == 60
        return Response(body=payload, url=request.full_url, content_length=len(payload))

    settings = get_settings()
    monkeypatch.setenv("SOCIUM_RELEASE_MANIFEST", "https://updates.example/manifest.json")
    monkeypatch.setenv("SOCIUM_APP_VERSION", "1.0.5")
    monkeypatch.setenv("SOCIUM_RELEASE_TARGET", "win32-x64")
    monkeypatch.setenv("SOCIUM_RUNTIME_DIR", str(settings.data_dir.parent / "runtimes" / "1.0.5" / "win32-x64"))
    monkeypatch.setattr("app.lifecycle_service.urllib.request.urlopen", fake_urlopen)
    events = [json.loads(line) for line in prepare_update_stream()]
    assert [event["percentage"] for event in events if event["status"] == "downloading"] == list(range(101))
    assert events[-1]["status"] == "ready"
    assert (settings.data_dir / ".updates" / "bundle.tar.gz").read_bytes() == payload
    prepared = json.loads((settings.data_dir / ".updates" / "prepared-manifest.json").read_text(encoding="utf-8"))
    assert prepared["assets"]["win32-x64"]["sha256"] == checksum
