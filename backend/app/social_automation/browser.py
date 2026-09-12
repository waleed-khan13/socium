from __future__ import annotations

import asyncio
import json
import os
import shutil
import signal
import subprocess
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from uuid import UUID

from app.config import get_settings
from app.social_automation.contracts import BrowserError


def runtime_path() -> Path:
    return get_settings().models_dir / "browser-runtime"


def profile_path(account_id: str) -> Path:
    try:
        if str(UUID(account_id)) != account_id:
            raise ValueError
    except ValueError as error:
        raise BrowserError("INVALID_PROFILE", "Invalid local browser profile.") from error
    root = get_settings().data_dir / "browser_profiles"
    target = root / "linkedin" / account_id
    # Never follow a replaced profile/root into another directory.
    for path in (root, root / "linkedin", target):
        if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
            raise BrowserError("INVALID_PROFILE", "Browser profile links are not supported.")
    if not target.resolve().is_relative_to(root.resolve()):
        raise BrowserError("INVALID_PROFILE", "Invalid local browser profile location.")
    return target


@contextmanager
def exclusive_browser() -> Iterator[None]:
    """One OS-released lock for all Socium browsers, across processes."""
    lock_path = get_settings().data_dir / ".browser-operation.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise BrowserError(
                "BROWSER_BUSY", "Another browser operation is active. Try again after it finishes."
            ) from error
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def driver_paths() -> tuple[Path, Path]:
    import playwright

    root = Path(playwright.__file__).parent / "driver"
    return root / ("node.exe" if os.name == "nt" else "node"), root / "package" / "cli.js"


def browser_installed() -> bool:
    try:
        _, cli = driver_paths()
        metadata = json.loads((cli.parent / "browsers.json").read_text(encoding="utf-8"))
        browser = next(b for b in metadata["browsers"] if b["name"] == "chromium")
        revisions = {str(browser["revision"]), *map(str, browser.get("revisionOverrides", {}).values())}
        for revision in revisions:
            root = runtime_path() / f"chromium-{revision}"
            if (root / "INSTALLATION_COMPLETE").is_file():
                return True
    except (ImportError, OSError, ValueError, KeyError, StopIteration):
        pass
    return False


def driver_available() -> bool:
    try:
        node, cli = driver_paths()
        return node.is_file() and cli.is_file() and (cli.parent / "browsers.json").is_file()
    except ImportError:
        return False


async def install_browser(progress: Callable[[str, int], None]) -> None:
    with exclusive_browser():
        node, cli = driver_paths()
        environment = {**os.environ, "PLAYWRIGHT_BROWSERS_PATH": str(runtime_path())}
        progress("Downloading the optional Chromium browser. This may take several minutes.", 5)
        process = await asyncio.create_subprocess_exec(
            str(node),
            str(cli),
            "install",
            "chromium",
            "--no-shell",
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            start_new_session=os.name != "nt",
        )
        try:
            async with asyncio.timeout(1770):
                while process.returncode is None:
                    progress("Installing Chromium; keep Socium running. Cancel is available.", 10)
                    try:
                        await asyncio.wait_for(process.wait(), timeout=1)
                    except TimeoutError:
                        continue
            if process.returncode != 0 or not browser_installed():
                raise BrowserError(
                    "BROWSER_INSTALL_FAILED",
                    "Browser installation failed. Check your network and retry. Linux may also need Chromium system libraries.",
                )
            progress("Browser installed. You can now open the login window.", 100)
        except TimeoutError as error:
            raise BrowserError(
                "BROWSER_INSTALL_TIMEOUT", "Browser download timed out. Check your network and retry."
            ) from error
        finally:
            if process.returncode is None:
                if os.name == "nt":
                    terminator = await asyncio.create_subprocess_exec(
                        "taskkill",
                        "/pid",
                        str(process.pid),
                        "/t",
                        "/f",
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                    await terminator.wait()
                    if process.returncode is None:
                        try:
                            process.kill()
                        except ProcessLookupError:
                            pass
                else:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                await process.wait()


@asynccontextmanager
async def open_browser(account_id: str, *, visible: bool = False) -> AsyncIterator[object]:
    from playwright.async_api import async_playwright

    if not browser_installed():
        raise BrowserError("BROWSER_NOT_INSTALLED", "Install the optional publishing browser first.")
    with exclusive_browser():
        profile = profile_path(account_id)
        profile.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(runtime_path())
        async with async_playwright() as driver:
            context = await driver.chromium.launch_persistent_context(
                str(profile),
                channel="chromium",
                headless=not visible,
                accept_downloads=False,
                viewport={"width": 1280, "height": 900},
            )
            context.set_default_timeout(12_000)
            context.set_default_navigation_timeout(30_000)
            try:
                page = context.pages[0] if context.pages else await context.new_page()
                yield page
            finally:
                await context.close()


def remove_profile(account_id: str, forget: Callable[[], None]) -> None:
    with exclusive_browser():
        profile = profile_path(account_id)
        if profile.exists():
            shutil.rmtree(profile)
        forget()
