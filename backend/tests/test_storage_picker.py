from __future__ import annotations

from pathlib import Path

import pytest

from app.errors import AppError
from app.native_storage import _windows_picker


def test_storage_picker_returns_the_native_selection(client, monkeypatch, tmp_path: Path) -> None:
    selected = tmp_path / "socium-data"
    selected.mkdir()
    monkeypatch.setattr("app.main.pick_storage_directory", lambda purpose: str(selected))

    response = client.post("/api/storage/pick-directory", json={"purpose": "data"})

    assert response.status_code == 200
    assert response.json() == {"ok": True, "cancelled": False, "path": str(selected)}


def test_storage_picker_reports_cancel_without_changing_any_path(client, monkeypatch) -> None:
    monkeypatch.setattr("app.main.pick_storage_directory", lambda purpose: None)

    response = client.post("/api/storage/pick-directory", json={"purpose": "models"})

    assert response.status_code == 200
    assert response.json() == {"ok": True, "cancelled": True, "path": None}


def test_windows_picker_uses_the_native_helper_without_powershell(
    monkeypatch, tmp_path: Path
) -> None:
    helper = tmp_path / "socium-windows-helper.exe"
    helper.write_bytes(b"fixture")
    selected = tmp_path / "selected"
    selected.mkdir()
    captured: list[str] = []

    def fake_run(command: list[str]) -> str:
        captured.extend(command)
        return f'{{"path": "{str(selected).replace(chr(92), chr(92) * 2)}"}}'

    monkeypatch.setenv("SOCIUM_WINDOWS_HELPER", str(helper))
    monkeypatch.setattr("app.native_storage._run_picker", fake_run)

    assert _windows_picker("Choose Socium data", tmp_path) == str(selected)
    assert captured[:2] == [str(helper), "pick-folder"]
    assert "powershell" not in " ".join(captured).lower()


def test_windows_picker_rejects_invalid_helper_output(monkeypatch, tmp_path: Path) -> None:
    helper = tmp_path / "socium-windows-helper.exe"
    helper.write_bytes(b"fixture")
    monkeypatch.setenv("SOCIUM_WINDOWS_HELPER", str(helper))
    monkeypatch.setattr("app.native_storage._run_picker", lambda command: "not-json")

    with pytest.raises(AppError, match="invalid response"):
        _windows_picker("Choose Socium models", tmp_path)


def test_storage_move_is_forwarded_to_the_authenticated_runtime_controller(
    client, monkeypatch, tmp_path: Path
) -> None:
    data_directory = tmp_path / "selected-data"
    models_directory = tmp_path / "selected-models"
    data_directory.mkdir()
    models_directory.mkdir()
    captured: dict[str, str] = {}

    def fake_move(data: str, models: str):
        captured.update({"data": data, "models": models})
        return {"action": "storage-move", "restarting": True}

    monkeypatch.setattr("app.main.request_storage_move", fake_move)
    response = client.post(
        "/api/storage/move",
        json={"dataDir": str(data_directory), "modelsDir": str(models_directory)},
    )

    assert response.status_code == 200
    assert response.json()["restarting"] is True
    assert captured == {
        "data": str(data_directory.resolve()),
        "models": str(models_directory.resolve()),
    }
