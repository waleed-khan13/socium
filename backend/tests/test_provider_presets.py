from __future__ import annotations

import asyncio

import pytest

from app.errors import ExternalServiceError
from app.services import provider


@pytest.mark.parametrize(
    ("kind", "base_url", "expected_url", "expected_header"),
    [
        (
            "openai",
            "https://api.openai.com/v1",
            "https://api.openai.com/v1/models",
            ("Authorization", "Bearer test-key"),
        ),
        (
            "gemini",
            "https://generativelanguage.googleapis.com/v1beta/openai",
            "https://generativelanguage.googleapis.com/v1beta/openai/models",
            ("Authorization", "Bearer test-key"),
        ),
        (
            "anthropic",
            "https://api.anthropic.com/v1",
            "https://api.anthropic.com/v1/models",
            ("x-api-key", "test-key"),
        ),
        (
            "openrouter",
            "https://openrouter.ai/api/v1",
            "https://openrouter.ai/api/v1/models",
            ("Authorization", "Bearer test-key"),
        ),
        (
            "nvidia",
            "https://integrate.api.nvidia.com/v1",
            "https://integrate.api.nvidia.com/v1/models",
            ("Authorization", "Bearer test-key"),
        ),
    ],
)
def test_hosted_presets_use_exact_model_endpoints(
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
    base_url: str,
    expected_url: str,
    expected_header: tuple[str, str],
) -> None:
    calls: list[dict[str, object]] = []

    async def fake_request(url: str, **kwargs):
        calls.append({"url": url, **kwargs})
        return {"data": [{"id": "visible-model"}]}

    monkeypatch.setattr(provider, "_request_json", fake_request)
    result = asyncio.run(
        provider.test_provider(
            {"kind": kind, "base_url": base_url, "model": "visible-model", "api_key": "test-key"}
        )
    )

    assert result.ok is True
    assert result.models == ["visible-model"]
    assert calls[0]["url"] == expected_url
    headers = calls[0]["headers"]
    assert isinstance(headers, dict)
    assert headers[expected_header[0]] == expected_header[1]
    if kind == "anthropic":
        assert headers["anthropic-version"] == "2023-06-01"
        assert "Authorization" not in headers
    if kind == "openrouter":
        assert headers["X-Title"] == "Socium"


def test_hosted_preset_rejects_a_non_official_endpoint() -> None:
    with pytest.raises(ExternalServiceError, match="fixed official API endpoint"):
        provider.validate_provider_base_url("openai", "https://credential-capture.example/v1")


def test_generation_prompt_uses_only_confirmed_brand_preferences() -> None:
    request = {
        "channel": "linkedin",
        "topic": "A useful workflow",
        "objective": "Teach one practical lesson",
        "tone": "Direct",
    }
    unconfirmed = provider._generation_prompt(
        request,
        {
            "business_name": "Northstar",
            "business_description": "A private marketing tool.",
            "profile_confirmed": False,
            "restricted_claims": ["This must stay private"],
        },
    )
    assert "Northstar" in unconfirmed
    assert "This must stay private" not in unconfirmed
    assert "Confirmed brand profile revision" not in unconfirmed

    confirmed = provider._generation_prompt(
        request,
        {
            "business_name": "Northstar",
            "business_description": "A private marketing tool.",
            "profile_confirmed": True,
            "profile_version": 3,
            "website": "https://northstar.example",
            "industry": "Marketing technology",
            "products_services": "Reviewed social publishing",
            "target_audience": "Privacy-conscious service businesses",
            "location": "Pakistan",
            "goals": ["Build trust"],
            "call_to_action": "Book a workflow review",
            "language": "Roman Urdu",
            "tone": "Practical and calm",
            "content_pillars": ["Local AI", "Human approval"],
            "restricted_claims": ["Guaranteed growth"],
            "branded_hashtags": ["#Socium"],
            "visual_style": "Dark editorial",
            "brand_colors": ["#f59e0b", "#18181b", "#10b981"],
        },
    )
    assert "Confirmed brand profile revision: 3" in confirmed
    assert "Preferred language: Roman Urdu" in confirmed
    assert "Restricted claims or topics: Guaranteed growth" in confirmed
    assert "Branded hashtags: #Socium" in confirmed


def test_anthropic_generation_uses_the_native_messages_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    async def fake_request(url: str, **kwargs):
        calls.append({"url": url, **kwargs})
        return {"content": [{"type": "text", "text": '{"title":"Ready"}'}]}

    monkeypatch.setattr(provider, "_request_json", fake_request)
    output = asyncio.run(
        provider._generate_json_text(
            {
                "kind": "anthropic",
                "base_url": "https://api.anthropic.com/v1",
                "model": "claude-sonnet-4-6",
                "api_key": "anthropic-key",
            },
            "Draft a post",
            system_prompt="Stay factual",
            temperature=0.5,
        )
    )

    assert output == '{"title":"Ready"}'
    assert calls[0]["url"] == "https://api.anthropic.com/v1/messages"
    headers = calls[0]["headers"]
    body = calls[0]["json_body"]
    assert isinstance(headers, dict)
    assert isinstance(body, dict)
    assert headers["x-api-key"] == "anthropic-key"
    assert headers["anthropic-version"] == "2023-06-01"
    assert body["system"] == "Stay factual"
    assert body["messages"] == [{"role": "user", "content": "Draft a post"}]
    assert all(message.get("role") != "system" for message in body["messages"])


def test_anthropic_compatible_gateway_uses_one_selected_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    async def fake_request(url: str, **kwargs):
        calls.append({"url": url, **kwargs})
        return {"data": [{"id": "gateway-claude", "display_name": "Gateway Claude"}]}

    monkeypatch.setattr(provider, "_request_json", fake_request)
    result = asyncio.run(
        provider.discover_provider(
            "https://gateway.example/v1",
            protocol_hint="anthropic-compatible",
            api_key="one-scoped-key",
        )
    )

    assert result["ok"] is True
    assert result["detectedKind"] == "anthropic-compatible"
    assert result["models"] == ["gateway-claude"]
    assert len(calls) == 1
    assert calls[0]["url"] == "https://gateway.example/v1/models"
    assert calls[0]["headers"] == {
        "x-api-key": "one-scoped-key",
        "anthropic-version": "2023-06-01",
    }


def test_credential_free_discovery_detects_ollama_and_openai_shapes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ollama_calls: list[dict[str, object]] = []

    async def fake_ollama(url: str, **kwargs):
        ollama_calls.append({"url": url, **kwargs})
        return {"models": [{"name": "qwen3.5:4b"}]}

    monkeypatch.setattr(provider, "_request_json", fake_ollama)
    ollama = asyncio.run(provider.discover_provider("http://127.0.0.1:11434"))
    assert ollama["detectedKind"] == "ollama"
    assert ollama["models"] == ["qwen3.5:4b"]
    assert "headers" not in ollama_calls[0]

    openai_calls: list[dict[str, object]] = []

    async def fake_openai(url: str, **kwargs):
        openai_calls.append({"url": url, **kwargs})
        if url.endswith("/api/tags"):
            raise ExternalServiceError("not Ollama")
        return {"data": [{"id": "local-model", "object": "model", "owned_by": "local"}]}

    monkeypatch.setattr(provider, "_request_json", fake_openai)
    openai = asyncio.run(provider.discover_provider("http://127.0.0.1:1234/v1"))
    assert openai["detectedKind"] == "openai-compatible"
    assert openai["models"] == ["local-model"]
    assert len(openai_calls) == 2
    assert all("headers" not in call for call in openai_calls)


def test_unknown_authenticated_endpoint_requires_protocol_before_using_a_key(
    monkeypatch: pytest.MonkeyPatch,
    client,
) -> None:
    calls: list[str] = []

    async def blocked(url: str, **_kwargs):
        calls.append(url)
        raise ExternalServiceError("authentication required")

    monkeypatch.setattr(provider, "_request_json", blocked)
    result = asyncio.run(provider.discover_provider("https://private-gateway.example/v1"))
    assert result["ok"] is False
    assert result["requiresProtocolChoice"] is True
    assert result["candidates"] == ["openai-compatible", "anthropic-compatible", "ollama"]
    assert len(calls) == 2

    rejected = client.post(
        "/api/providers/discover",
        json={
            "baseUrl": "https://private-gateway.example/v1",
            "protocolHint": "auto",
            "apiKey": "must-not-be-sprayed",
        },
    )
    assert rejected.status_code == 422
    assert "Choose one API protocol" in rejected.json()["error"]


def test_ollama_generation_sets_a_bounded_idle_unload_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    async def fake_request(url: str, **kwargs):
        calls.append({"url": url, **kwargs})
        return {"message": {"content": '{"title":"Local"}'}}

    monkeypatch.setattr(provider, "_request_json", fake_request)
    output = asyncio.run(
        provider._generate_json_text(
            {"kind": "ollama", "base_url": "http://127.0.0.1:11434", "model": "qwen3.5:4b", "api_key": ""},
            "Draft locally",
            system_prompt="Stay factual",
            temperature=0.5,
        )
    )
    assert output == '{"title":"Local"}'
    assert calls[0]["json_body"]["keep_alive"] == "2m"


def test_provider_settings_accept_local_auto_detection_and_presets(client) -> None:
    local = client.put(
        "/api/settings/provider",
        json={
            "kind": "ollama",
            "baseUrl": "http://127.0.0.1:11434",
            "model": "",
            "apiKey": "",
        },
    )
    assert local.status_code == 200
    assert local.json()["state"]["provider"]["configured"] is False

    hosted = client.put(
        "/api/settings/provider",
        json={
            "kind": "openai",
            "baseUrl": "https://api.openai.com/v1",
            "model": "gpt-5.6-luna",
            "apiKey": "encrypted-openai-key",
        },
    )
    assert hosted.status_code == 200
    public = hosted.json()["state"]["provider"]
    assert public == {
        "kind": "openai",
        "baseUrl": "https://api.openai.com/v1",
        "model": "gpt-5.6-luna",
        "hasApiKey": True,
        "configured": True,
        "verified": False,
        "updatedAt": public["updatedAt"],
    }

    rejected = client.put(
        "/api/settings/provider",
        json={
            "kind": "openai",
            "baseUrl": "https://credential-capture.example/v1",
            "model": "gpt-5.6-luna",
            "apiKey": "must-not-be-sent",
        },
    )
    assert rejected.status_code == 400
    assert "fixed official API endpoint" in rejected.json()["error"]
