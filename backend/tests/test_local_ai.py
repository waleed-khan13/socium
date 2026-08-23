from __future__ import annotations

import asyncio
import json

import pytest

from app.services import local_ai


def test_system_profile_recommends_a_bounded_model_for_detected_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(local_ai, "_total_memory_bytes", lambda: 12 * 1024**3)
    monkeypatch.setattr(local_ai, "_nvidia_gpu", lambda: None)
    profile = local_ai.system_profile()
    assert profile["recommendedModel"] == "qwen3.5:4b"
    assert profile["recommendationTier"] == "recommended"


def test_local_status_lists_models_without_auto_selecting_an_unsafe_unknown_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_request(_url: str, **_kwargs):
        return {"models": [{"name": "already-installed:latest"}]}

    monkeypatch.setattr(local_ai, "_request_json", fake_request)
    monkeypatch.setattr(
        local_ai,
        "system_profile",
        lambda: {
            "platform": "test",
            "architecture": "x64",
            "memoryBytes": 16 * 1024**3,
            "gpu": None,
            "recommendedModel": "qwen3.5:4b",
            "recommendationTier": "recommended",
            "recommendationReason": "test",
        },
    )
    monkeypatch.setattr(local_ai.shutil, "which", lambda _name: "ollama")
    status = asyncio.run(local_ai.local_ai_status("http://127.0.0.1:11434"))
    assert status["ollamaInstalled"] is True
    assert status["ollamaRunning"] is True
    assert status["models"] == ["already-installed:latest"]
    assert status["selectedRecommendation"] == "qwen3.5:4b"
    assert status["recommendedModelInstalled"] is False


def test_model_pull_stream_reports_every_percentage_and_verifies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_request(_url: str, **_kwargs):
        return {"models": [{"name": "qwen3.5:4b"}]}

    class FakeResponse:
        is_success = True
        status_code = 200

        async def aiter_lines(self):
            yield json.dumps({"status": "pulling", "total": 100, "completed": 3})
            yield json.dumps({"status": "success", "total": 100, "completed": 100})

    class FakeStream:
        async def __aenter__(self):
            return FakeResponse()

        async def __aexit__(self, *_args):
            return False

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        def stream(self, *_args, **_kwargs):
            return FakeStream()

    monkeypatch.setattr(local_ai, "_request_json", fake_request)
    monkeypatch.setattr(local_ai.httpx, "AsyncClient", FakeClient)

    async def collect() -> list[dict[str, object]]:
        raw = [chunk async for chunk in local_ai.stream_ollama_pull("http://127.0.0.1:11434", "qwen3.5:4b")]
        return [json.loads(line) for line in b"".join(raw).decode().splitlines()]

    events = asyncio.run(collect())
    percentages = [event["percentage"] for event in events]
    assert percentages == list(range(101))
    assert events[-1] == {
        "ok": True,
        "status": "Model verified",
        "percentage": 100,
        "verified": True,
    }
