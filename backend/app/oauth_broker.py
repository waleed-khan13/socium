from __future__ import annotations

import asyncio
import base64
import hashlib
import html
import secrets
import time
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx

from app.config import get_settings
from app.connector_store import upsert_oauth_connector
from app.connectors.service import test_saved_connector
from app.errors import AppError
from app.schemas import ConnectorAccountUpsert

OAuthProvider = Literal["slack", "linkedin"]
SESSION_TTL_SECONDS = 10 * 60


def _token() -> str:
    return secrets.token_urlsafe(48)


def _challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _broker_url() -> str:
    value = get_settings().connect_broker_url
    if not value:
        raise AppError(
            "One-click connections are not active in this build yet. The Socium maintainer must deploy the connection broker.",
            503,
        )
    parsed = urlsplit(value)
    loopback = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    if parsed.scheme != "https" and not (parsed.scheme == "http" and loopback):
        raise AppError("Socium connection broker must use HTTPS.", 503)
    return value


@dataclass(slots=True)
class OAuthSession:
    id: str
    provider: OAuthProvider
    local_state: str
    verifier: str
    created_at: float
    status: str = "waiting"
    account_id: str | None = None
    message: str = "Waiting for provider approval."

    def public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "provider": self.provider,
            "status": self.status,
            "accountId": self.account_id,
            "message": self.message,
            "expiresIn": max(0, int(SESSION_TTL_SECONDS - (time.monotonic() - self.created_at))),
        }


class OAuthBroker:
    def __init__(self) -> None:
        self._sessions: dict[str, OAuthSession] = {}
        self._lock = asyncio.Lock()

    def configured(self) -> bool:
        try:
            _broker_url()
        except AppError:
            return False
        return True

    async def start(self, provider: OAuthProvider) -> dict[str, Any]:
        broker_url = _broker_url()
        verifier = _token()
        local_state = _token()
        session_id = _token()
        settings = get_settings()
        callback = f"http://127.0.0.1:{settings.port}/oauth/callback"
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
                response = await client.post(
                    f"{broker_url}/v1/sessions",
                    json={
                        "provider": provider,
                        "localCallback": callback,
                        "localState": local_state,
                        "codeChallenge": _challenge(verifier),
                    },
                    headers={"accept": "application/json"},
                )
            payload = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise AppError("Socium's one-click connection service is temporarily unavailable.", 503) from error
        authorization_url = str(payload.get("authorizationUrl") or "") if isinstance(payload, dict) else ""
        if not response.is_success or not authorization_url.startswith("https://"):
            raise AppError("Socium's one-click connection service rejected this request.", 503)
        session = OAuthSession(session_id, provider, local_state, verifier, time.monotonic())
        async with self._lock:
            self._cleanup()
            self._sessions[session_id] = session
        return {**session.public_dict(), "authorizationUrl": authorization_url}

    async def status(self, session_id: str) -> dict[str, Any]:
        async with self._lock:
            self._cleanup()
            session = self._sessions.get(session_id)
            if session is None:
                raise AppError("Connection attempt expired. Start again.", 404)
            return session.public_dict()

    async def disconnect_slack(self, relay_token: str) -> None:
        if not relay_token or not self.configured():
            return
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
                await client.post(
                    f"{_broker_url()}/v1/slack/disconnect",
                    json={"relayToken": relay_token},
                )
        except httpx.HTTPError:
            # Local removal must not be blocked by a temporarily unreachable relay.
            return

    async def complete(
        self,
        provider: str,
        local_state: str,
        handoff_code: str,
        provider_error: str,
    ) -> OAuthSession:
        async with self._lock:
            self._cleanup()
            session = next(
                (item for item in self._sessions.values() if item.local_state == local_state),
                None,
            )
            if session is None or session.provider != provider or session.status != "waiting":
                raise AppError("This connection attempt is invalid or expired.", 400)
            if provider_error:
                session.status = "error"
                session.message = "Connection was cancelled or rejected by the provider."
                return session
            session.status = "finishing"

        try:
            connector = await self._exchange(session, handoff_code)
            account = upsert_oauth_connector(connector)
            result = await test_saved_connector(str(account["id"]))
        except Exception as error:  # noqa: BLE001 - store a safe OAuth result for polling UI.
            async with self._lock:
                session.status = "error"
                session.message = error.message if isinstance(error, AppError) else "Connection could not be completed."
            return session

        async with self._lock:
            session.status = "connected"
            session.account_id = str(account["id"])
            session.message = result.message
        return session

    async def _exchange(
        self,
        session: OAuthSession,
        handoff_code: str,
    ) -> ConnectorAccountUpsert:
        if not handoff_code:
            raise AppError("Connection handoff code is missing.")
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
                response = await client.post(
                    f"{_broker_url()}/v1/handoffs/exchange",
                    json={
                        "provider": session.provider,
                        "localState": session.local_state,
                        "codeVerifier": session.verifier,
                        "handoffCode": handoff_code,
                    },
                    headers={"accept": "application/json"},
                )
            payload = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise AppError("Secure connection handoff failed.", 503) from error
        raw = payload.get("connector") if response.is_success and isinstance(payload, dict) else None
        if not isinstance(raw, dict) or raw.get("adapterId") != session.provider:
            raise AppError("Secure connection handoff was invalid or expired.")
        return ConnectorAccountUpsert.model_validate(
            {
                "adapterId": raw.get("adapterId"),
                "name": raw.get("name"),
                "config": raw.get("config") or {},
                "secrets": raw.get("secrets") or {},
                "scopes": raw.get("scopes") or [],
                "enabled": bool(raw.get("enabled", True)),
            }
        )

    def _cleanup(self) -> None:
        expired = [
            key
            for key, session in self._sessions.items()
            if time.monotonic() - session.created_at > SESSION_TTL_SECONDS
        ]
        for key in expired:
            self._sessions.pop(key, None)


def callback_html(session: OAuthSession) -> str:
    success = session.status == "connected"
    title = "Connected to Socium" if success else "Connection not completed"
    message = session.message
    return (
        "<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
        f"<title>{html.escape(title)}</title>"
        "<style>body{background:#050505;color:#eee;font:16px/1.55 system-ui;margin:0;display:grid;"
        "min-height:100vh;place-items:center}.card{border:1px solid #292929;border-radius:14px;"
        "max-width:620px;padding:28px;background:#090909}h1{font-size:22px;margin:0 0 10px}"
        "p{color:#aaa;margin:0}</style>"
        f"<main class='card'><h1>{html.escape(title)}</h1><p>{html.escape(message)}</p></main>"
        "<script>setTimeout(()=>window.close(),1200)</script>"
    )


oauth_broker = OAuthBroker()
