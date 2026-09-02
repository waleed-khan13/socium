from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Literal

from app.config import get_settings
from app.errors import AppError

PickerPurpose = Literal["data", "models"]


def _run_picker(command: list[str]) -> str | None:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
            timeout=300,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise AppError("The native folder picker could not be opened on this computer.") from error
    if result.returncode != 0:
        return None
    values = result.stdout.strip().splitlines()
    return values[-1].strip() if values else None


def _windows_picker(title: str, initial: Path) -> str | None:
    configured = os.getenv("SOCIUM_WINDOWS_HELPER", "").strip()
    candidates = [Path(configured)] if configured else []
    candidates.extend(
        [
            Path(__file__).resolve().parents[2]
            / "native"
            / "windows-helper"
            / "target"
            / "release"
            / "socium-windows-helper.exe",
            get_settings().runtime_dir / "native" / "socium-windows-helper.exe",
        ]
    )
    helper = next((candidate for candidate in candidates if candidate.is_file()), None)
    if helper is None:
        raise AppError("The Socium Windows native helper is missing. Reinstall or update Socium.")
    response = _run_picker(
        [
            str(helper),
            "pick-folder",
            "--title",
            title,
            "--initial",
            str(initial),
        ]
    )
    if not response:
        return None
    try:
        payload = json.loads(response)
    except json.JSONDecodeError as error:
        raise AppError("The Windows folder picker returned an invalid response.") from error
    selected = payload.get("path")
    return str(selected).strip() if selected else None


def _macos_picker(title: str, initial: Path) -> str | None:
    script = f'POSIX path of (choose folder with prompt "{title}" default location POSIX file "{initial}")'
    return _run_picker(["osascript", "-e", script])


def _linux_picker(title: str, initial: Path) -> str | None:
    if executable := shutil.which("zenity"):
        return _run_picker(
            [executable, "--file-selection", "--directory", f"--title={title}", f"--filename={initial}{os.sep}"]
        )
    if executable := shutil.which("kdialog"):
        return _run_picker([executable, "--getexistingdirectory", str(initial), "--title", title])
    raise AppError("Install Zenity or KDialog to use the native folder picker on Linux.")


def validate_storage_destination(value: str, purpose: PickerPurpose) -> Path:
    try:
        selected = Path(value).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise AppError("Choose an existing folder that Socium can access.") from error
    if not selected.is_dir():
        raise AppError("Choose a folder, not a file.")
    home = Path.home().resolve()
    root = Path(selected.anchor).resolve()
    if selected in {home, root}:
        raise AppError("Choose a dedicated folder, not an entire drive or home directory.")
    settings = get_settings()
    runtime = settings.runtime_dir.resolve()
    if selected == runtime or runtime in selected.parents or selected in runtime.parents:
        raise AppError("Storage cannot be placed inside Socium's replaceable program directory.")
    current_other = settings.models_dir.resolve() if purpose == "data" else settings.data_dir.resolve()
    if selected == current_other or selected in current_other.parents or current_other in selected.parents:
        raise AppError("Data and local AI models must use separate folders.")
    try:
        probe = selected / f".socium-write-test-{os.getpid()}"
        probe.write_bytes(b"")
        probe.unlink()
    except OSError as error:
        raise AppError("Socium cannot write to the selected folder. Choose another location.") from error
    return selected


def pick_storage_directory(purpose: PickerPurpose) -> str | None:
    settings = get_settings()
    current = settings.data_dir if purpose == "data" else settings.models_dir
    initial = current if current.exists() else current.parent
    title = "Choose Socium data folder" if purpose == "data" else "Choose Socium local AI models folder"
    system = platform.system()
    if system == "Windows":
        selected = _windows_picker(title, initial)
    elif system == "Darwin":
        selected = _macos_picker(title, initial)
    else:
        selected = _linux_picker(title, initial)
    if not selected:
        return None
    return str(validate_storage_destination(selected, purpose))
