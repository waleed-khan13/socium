from __future__ import annotations

import asyncio
import ctypes
import json
import os
import platform
import shutil
import subprocess
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.config import get_settings
from app.errors import ExternalServiceError
from app.services.provider import _request_json, validate_base_url


def _total_memory_bytes() -> int:
    if os.name == "nt":

        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong),
                ("memory_load", ctypes.c_ulong),
                ("total_physical", ctypes.c_ulonglong),
                ("available_physical", ctypes.c_ulonglong),
                ("total_page_file", ctypes.c_ulonglong),
                ("available_page_file", ctypes.c_ulonglong),
                ("total_virtual", ctypes.c_ulonglong),
                ("available_virtual", ctypes.c_ulonglong),
                ("available_extended_virtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.length = ctypes.sizeof(MemoryStatus)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return int(status.total_physical)
    try:
        return int(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES"))
    except (AttributeError, OSError, ValueError):
        return 0


def _nvidia_gpu() -> dict[str, Any] | None:
    executable = shutil.which("nvidia-smi")
    if not executable:
        return None
    try:
        result = subprocess.run(
            [
                executable,
                "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            check=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            text=True,
            timeout=3,
        )
        first = result.stdout.strip().splitlines()[0]
        name, memory = [part.strip() for part in first.rsplit(",", 1)]
        return {"name": name[:160], "memoryBytes": int(memory) * 1024 * 1024}
    except (IndexError, OSError, subprocess.SubprocessError, ValueError):
        return None


def system_profile() -> dict[str, Any]:
    memory_bytes = _total_memory_bytes()
    gpu = _nvidia_gpu()
    effective_memory = max(memory_bytes, int(gpu["memoryBytes"]) if gpu else 0)
    if effective_memory >= 24 * 1024**3:
        model, tier = "qwen3.5:9b", "balanced"
        rationale = "Enough detected memory for a stronger local writing model."
    elif effective_memory >= 8 * 1024**3:
        model, tier = "qwen3.5:4b", "recommended"
        rationale = "A compact multilingual model that fits typical modern laptops."
    else:
        model, tier = "qwen3.5:2b", "lightweight"
        rationale = "A smaller model reduces memory pressure on this computer."
    return {
        "platform": platform.system().lower(),
        "architecture": platform.machine().lower(),
        "memoryBytes": memory_bytes,
        "gpu": gpu,
        "recommendedModel": model,
        "recommendationTier": tier,
        "recommendationReason": rationale,
    }


async def local_ai_status(base_url: str) -> dict[str, Any]:
    normalized = validate_base_url(base_url)
    profile = system_profile()
    models: list[str] = []
    running = False
    error: str | None = None
    try:
        # Loopback either answers quickly or is unavailable. Interactive status
        # checks must not inherit hosted-provider retries and backoff delays.
        payload = await _request_json(
            f"{normalized}/api/tags",
            timeout=2,
            max_attempts=1,
        )
        raw_models = payload.get("models") if isinstance(payload.get("models"), list) else []
        models = [
            str(item.get("name")) for item in raw_models if isinstance(item, dict) and item.get("name")
        ][:50]
        running = True
    except ExternalServiceError as caught:
        error = caught.message
    # Never auto-select an arbitrary installed model: it may be much larger than
    # the detected hardware can safely run. Advanced users can still select one.
    recommended = profile["recommendedModel"]
    return {
        **profile,
        "ollamaInstalled": shutil.which("ollama") is not None,
        "ollamaRunning": running,
        "baseUrl": normalized,
        "models": models,
        "selectedRecommendation": recommended,
        "recommendedModelInstalled": recommended in models,
        "modelsDirectory": str(get_settings().models_dir),
        "error": error,
    }


def _event(payload: dict[str, Any]) -> bytes:
    return f"{json.dumps(payload, separators=(',', ':'))}\n".encode()


async def stream_ollama_pull(base_url: str, model: str) -> AsyncIterator[bytes]:
    normalized = validate_base_url(base_url)
    # Fail before opening a long stream if this is not an Ollama endpoint.
    await _request_json(f"{normalized}/api/tags", timeout=3, max_attempts=1)
    last_percentage = -1
    timeout = httpx.Timeout(connect=10, read=None, write=30, pool=10)
    try:
        async with (
            httpx.AsyncClient(follow_redirects=False, timeout=timeout) as client,
            client.stream(
                "POST",
                f"{normalized}/api/pull",
                headers={"Accept": "application/x-ndjson"},
                json={"model": model, "stream": True},
            ) as response,
        ):
            if not response.is_success:
                raise ExternalServiceError(f"Ollama returned HTTP {response.status_code}.")
            async for line in response.aiter_lines():
                if not line or len(line) > 64_000:
                    continue
                try:
                    update = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(update, dict):
                    continue
                if update.get("error"):
                    raise ExternalServiceError(str(update["error"])[:500])
                total = int(update.get("total") or 0)
                completed = int(update.get("completed") or 0)
                current = min(99, int(completed * 100 / total)) if total > 0 else last_percentage
                if current > last_percentage:
                    for percentage in range(last_percentage + 1, current + 1):
                        yield _event(
                            {
                                "ok": True,
                                "status": str(update.get("status") or "Downloading model"),
                                "percentage": percentage,
                                "completedBytes": completed,
                                "totalBytes": total,
                            }
                        )
                    last_percentage = current
                elif update.get("status"):
                    yield _event(
                        {
                            "ok": True,
                            "status": str(update["status"]),
                            "percentage": max(0, last_percentage),
                            "completedBytes": completed,
                            "totalBytes": total,
                        }
                    )
    except (httpx.HTTPError, OSError) as error:
        yield _event({"ok": False, "error": f"Model download failed ({type(error).__name__})."})
        return
    except ExternalServiceError as error:
        yield _event({"ok": False, "error": error.message})
        return

    # Give Ollama a moment to commit its manifest, then verify the exact model.
    for attempt in range(5):
        try:
            payload = await _request_json(f"{normalized}/api/tags", timeout=5)
        except ExternalServiceError as error:
            if attempt == 4:
                yield _event({"ok": False, "error": f"Model verification failed: {error.message}"})
                return
            await asyncio.sleep(0.5)
            continue
        installed = {
            str(item.get("name"))
            for item in payload.get("models", [])
            if isinstance(item, dict) and item.get("name")
        }
        if model in installed or any(name.startswith(f"{model}:") for name in installed):
            yield _event({"ok": True, "status": "Model verified", "percentage": 100, "verified": True})
            return
        if attempt < 4:
            await asyncio.sleep(0.5)
    yield _event({"ok": False, "error": "Ollama finished downloading, but model verification failed."})
