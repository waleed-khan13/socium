from __future__ import annotations

import asyncio
import base64
import hashlib
from typing import Any, Self

import httpx
import pytest


def test_local_oauth_pkce_matches_s256() -> None:
    from app.oauth_broker import _challenge

    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    assert _challenge(verifier) == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def test_telegram_proxy_accepts_http_and_socks_but_rejects_other_schemes() -> None:
    from app.errors import ExternalServiceError
    from app.services.telegram import validate_proxy_url

    assert validate_proxy_url("http://127.0.0.1:8080") == "http://127.0.0.1:8080"
    assert validate_proxy_url("socks5://user:secret@127.0.0.1:1080").startswith("socks5://")
    with pytest.raises(ExternalServiceError):
        validate_proxy_url("file:///tmp/proxy")


def test_telegram_proxy_health_routes_the_probe_through_the_selected_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import telegram

    recorded: dict[str, Any] = {}

    class FakeResponse:
        status_code = 302

    class FakeClient:
        def __init__(self, **kwargs: Any) -> None:
            recorded.update(kwargs)

        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def get(self, url: str, *, headers: dict[str, str]) -> FakeResponse:
            recorded.update({"url": url, "headers": headers})
            return FakeResponse()

    monkeypatch.setattr(telegram.httpx, "AsyncClient", FakeClient)
    asyncio.run(telegram.test_proxy_connection("socks5://proxy.example:1080"))
    assert recorded["proxy"] == "socks5://proxy.example:1080"
    assert recorded["url"] == "https://api.telegram.org/"


def test_oauth_start_uses_dynamic_loopback_port_and_s256(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import get_settings
    from app.oauth_broker import OAuthBroker

    recorded: dict[str, Any] = {}

    class FakeResponse:
        is_success = True

        @staticmethod
        def json() -> dict[str, Any]:
            return {"authorizationUrl": "https://slack.com/oauth/v2/authorize?client_id=test"}

    class FakeClient:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def post(self, url: str, *, json: dict[str, Any], headers: dict[str, str]) -> FakeResponse:
            recorded.update({"url": url, "json": json, "headers": headers})
            return FakeResponse()

    monkeypatch.setenv("SOCIUM_CONNECT_BROKER_URL", "https://connect.socium.example")
    monkeypatch.setenv("SOCIUM_API_PORT", "8127")
    get_settings.cache_clear()
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    try:
        result = asyncio.run(OAuthBroker().start("slack"))
    finally:
        get_settings.cache_clear()

    payload = recorded["json"]
    assert result["authorizationUrl"].startswith("https://slack.com/")
    assert payload["localCallback"] == "http://127.0.0.1:8127/oauth/callback"
    assert len(payload["localState"]) >= 32
    challenge = payload["codeChallenge"]
    assert len(base64.urlsafe_b64decode(challenge + "==")) == hashlib.sha256().digest_size
