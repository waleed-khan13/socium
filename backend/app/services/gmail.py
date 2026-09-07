from __future__ import annotations

import asyncio
import base64
import re
from datetime import UTC, datetime
from email.utils import getaddresses, parseaddr
from html import unescape
from typing import Any
from urllib.parse import quote

import httpx

from app.config import get_settings
from app.errors import AppError, ExternalServiceError

GMAIL_API_BASE_URL = "https://gmail.googleapis.com/gmail/v1"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
MAX_SYNC_THREADS = 50


def _safe_provider_error(payload: object, status_code: int) -> str:
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = str(error.get("message") or "").strip()
            if message:
                return message[:500]
        if isinstance(error, str) and error.strip():
            return error.strip()[:500]
    return f"HTTP {status_code}"


async def gmail_api_request(
    access_token: str,
    resource: str,
    *,
    method: str = "GET",
    params: dict[str, str | int] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout: float = 20,
) -> dict[str, Any]:
    if not access_token or len(access_token) > 8_000:
        raise ExternalServiceError("Gmail access token is missing or invalid.")
    resource = resource.lstrip("/")
    url = f"{GMAIL_API_BASE_URL}/{resource}"
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            response = await client.request(
                method,
                url,
                params=params,
                json=json_body,
                headers={
                    "accept": "application/json",
                    "authorization": f"Bearer {access_token}",
                    **({"content-type": "application/json; charset=utf-8"} if json_body else {}),
                },
            )
        payload = response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise ExternalServiceError("Gmail is temporarily unavailable.") from error
    if not response.is_success or not isinstance(payload, dict):
        reason = _safe_provider_error(payload, response.status_code).replace(access_token, "[redacted]")
        raise ExternalServiceError(f"Gmail request failed: {reason}")
    return payload


async def test_gmail_connection(access_token: str) -> dict[str, str]:
    payload = await gmail_api_request(access_token, "users/me/profile", timeout=12)
    email_address = str(payload.get("emailAddress") or "").strip()
    if not email_address or "@" not in email_address:
        raise ExternalServiceError("Gmail profile did not return an email address.")
    return {
        "emailAddress": email_address,
        "historyId": str(payload.get("historyId") or ""),
        "messagesTotal": str(payload.get("messagesTotal") or "0"),
        "threadsTotal": str(payload.get("threadsTotal") or "0"),
    }


def _token_expiring(expires_at: str) -> bool:
    if not expires_at:
        return True
    try:
        parsed = datetime.fromisoformat(expires_at)
    except ValueError:
        return True
    return (parsed.astimezone(UTC) - datetime.now(UTC)).total_seconds() < 90


async def _refresh_access_token(refresh_token: str) -> dict[str, str]:
    broker = get_settings().connect_broker_url.rstrip("/")
    if not broker:
        raise AppError("Gmail needs Socium's one-click connection service to refresh access.", 503)
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
            response = await client.post(
                f"{broker}/v1/gmail/token/refresh",
                json={"refreshToken": refresh_token},
                headers={"accept": "application/json"},
            )
        payload = response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise ExternalServiceError("Gmail access could not be refreshed.") from error
    token = str(payload.get("accessToken") or "") if isinstance(payload, dict) else ""
    expires_at = str(payload.get("expiresAt") or "") if isinstance(payload, dict) else ""
    if not response.is_success or not token or not expires_at:
        raise ExternalServiceError("Gmail authorization expired. Reconnect Gmail in Integrations.")
    return {"access_token": token, "expires_at": expires_at}


async def gmail_access(account_id: str) -> tuple[dict[str, Any], str]:
    from app.connector_store import connector_runtime, replace_connector_credentials

    runtime = connector_runtime(account_id)
    if runtime["adapter_id"] != "gmail" or not runtime["enabled"]:
        raise AppError("Choose an enabled Gmail connector first.")
    access_token = str(runtime["secrets"].get("access_token") or "")
    if not _token_expiring(str(runtime["config"].get("expires_at") or "")):
        return runtime, access_token
    refresh_token = str(runtime["secrets"].get("refresh_token") or "")
    refreshed = await _refresh_access_token(refresh_token)
    replace_connector_credentials(
        account_id,
        secrets={"access_token": refreshed["access_token"]},
        config={**runtime["config"], "expires_at": refreshed["expires_at"]},
    )
    runtime["secrets"]["access_token"] = refreshed["access_token"]
    runtime["config"]["expires_at"] = refreshed["expires_at"]
    return runtime, refreshed["access_token"]


def _decode_body(value: str) -> str:
    if not value:
        return ""
    try:
        padded = value + "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")
    except (ValueError, UnicodeError):
        return ""


def _plain_text_part(payload: dict[str, Any]) -> str:
    mime_type = str(payload.get("mimeType") or "").lower()
    body = payload.get("body") if isinstance(payload.get("body"), dict) else {}
    if mime_type == "text/plain":
        return _decode_body(str(body.get("data") or ""))
    parts = payload.get("parts") if isinstance(payload.get("parts"), list) else []
    for part in parts:
        if isinstance(part, dict):
            text = _plain_text_part(part)
            if text:
                return text
    if mime_type == "text/html":
        html = _decode_body(str(body.get("data") or ""))
        return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", html))).strip()
    return ""


def _headers(payload: dict[str, Any]) -> dict[str, str]:
    headers = payload.get("headers") if isinstance(payload.get("headers"), list) else []
    return {
        str(item.get("name") or "").casefold(): str(item.get("value") or "").strip()
        for item in headers
        if isinstance(item, dict) and item.get("name")
    }


def normalize_gmail_thread(payload: dict[str, Any], account_email: str) -> dict[str, Any]:
    raw_messages = payload.get("messages") if isinstance(payload.get("messages"), list) else []
    messages: list[dict[str, Any]] = []
    participants: set[str] = set()
    unread = False
    for raw in raw_messages:
        if not isinstance(raw, dict):
            continue
        mime = raw.get("payload") if isinstance(raw.get("payload"), dict) else {}
        headers = _headers(mime)
        sender = headers.get("from", "")[:998]
        recipient_values = [headers.get("to", ""), headers.get("cc", "")]
        recipients = [address for _, address in getaddresses(recipient_values) if address]
        sender_address = parseaddr(sender)[1]
        labels = {str(value) for value in raw.get("labelIds", []) if isinstance(value, str)}
        direction = "outbound" if "SENT" in labels or sender_address.casefold() == account_email.casefold() else "inbound"
        unread = unread or (direction == "inbound" and "UNREAD" in labels)
        if sender_address:
            participants.add(sender_address)
        participants.update(recipients)
        try:
            sent_at = datetime.fromtimestamp(int(str(raw.get("internalDate") or "0")) / 1000, tz=UTC)
        except (TypeError, ValueError, OSError):
            sent_at = datetime.now(UTC)
        messages.append(
            {
                "providerMessageId": str(raw.get("id") or "")[:255],
                "internetMessageId": headers.get("message-id", "")[:998],
                "direction": direction,
                "sender": sender,
                "recipients": recipients[:100],
                "subject": headers.get("subject", "")[:998],
                "bodyText": _plain_text_part(mime)[:100_000],
                "snippet": str(raw.get("snippet") or "")[:2_000],
                "references": headers.get("references", "")[:8_000],
                "sentAt": sent_at.isoformat().replace("+00:00", "Z"),
            }
        )
    messages.sort(key=lambda item: item["sentAt"])
    latest = messages[-1] if messages else {}
    latest_inbound = next(
        (item for item in reversed(messages) if item.get("direction") == "inbound"),
        latest,
    )
    sender_name, sender_email = parseaddr(str(latest_inbound.get("sender") or ""))
    latest_direction = str(latest.get("direction") or "inbound")
    text = f"{latest.get('subject', '')} {latest.get('snippet', '')}".casefold()
    urgent = any(marker in text for marker in ("urgent", "asap", "today", "deadline", "immediately"))
    return {
        "providerThreadId": str(payload.get("id") or "")[:255],
        "historyId": str(payload.get("historyId") or "")[:255] or None,
        "subject": str(latest.get("subject") or "(No subject)")[:998],
        "snippet": str(latest.get("snippet") or "")[:2_000],
        "senderName": sender_name[:320],
        "senderEmail": sender_email[:320],
        "participants": sorted(participants)[:100],
        "classification": "needs_reply" if latest_direction == "inbound" else "waiting",
        "priority": "high" if urgent else "normal",
        "unread": unread,
        "lastMessageAt": str(latest.get("sentAt") or datetime.now(UTC).isoformat().replace("+00:00", "Z")),
        "messages": messages,
    }


async def fetch_gmail_threads(account_id: str, limit: int = 25) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    runtime, access_token = await gmail_access(account_id)
    account_email = str(runtime["config"].get("email_address") or "")
    listed = await gmail_api_request(
        access_token,
        "users/me/threads",
        params={"labelIds": "INBOX", "maxResults": max(1, min(limit, MAX_SYNC_THREADS))},
    )
    refs = [item for item in listed.get("threads", []) if isinstance(item, dict) and item.get("id")]
    semaphore = asyncio.Semaphore(5)

    async def load(item: dict[str, Any]) -> dict[str, Any]:
        async with semaphore:
            thread_id = quote(str(item["id"]), safe="")
            detail = await gmail_api_request(access_token, f"users/me/threads/{thread_id}", timeout=25)
            return normalize_gmail_thread(detail, account_email)

    threads = await asyncio.gather(*(load(item) for item in refs))
    return runtime, threads


def encode_gmail_reply(
    *,
    to_address: str,
    subject: str,
    body: str,
    internet_message_id: str,
    references: str,
    message_id: str,
) -> str:
    safe_subject = subject.replace("\r", " ").replace("\n", " ").strip()
    safe_to = to_address.replace("\r", "").replace("\n", "").strip()
    safe_internet_message_id = internet_message_id.replace("\r", "").replace("\n", "").strip()
    safe_references = references.replace("\r", " ").replace("\n", " ").strip()
    safe_message_id = message_id.replace("\r", "").replace("\n", "").strip()
    reference_values = " ".join(
        value for value in (safe_references, safe_internet_message_id) if value
    ).strip()
    headers = [
        f"To: {safe_to}",
        f"Subject: {safe_subject if safe_subject.casefold().startswith('re:') else f'Re: {safe_subject}'}",
        f"Message-ID: {safe_message_id}",
        "MIME-Version: 1.0",
        "Content-Type: text/plain; charset=UTF-8",
        "Content-Transfer-Encoding: 8bit",
    ]
    if safe_internet_message_id:
        headers.append(f"In-Reply-To: {safe_internet_message_id}")
    if reference_values:
        headers.append(f"References: {reference_values[:8_000]}")
    raw = "\r\n".join([*headers, "", body]).encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


async def send_gmail_reply(
    account_id: str,
    provider_thread_id: str,
    *,
    to_address: str,
    subject: str,
    body: str,
    internet_message_id: str,
    references: str,
    message_id: str,
) -> dict[str, Any]:
    _runtime, access_token = await gmail_access(account_id)
    return await gmail_api_request(
        access_token,
        "users/me/messages/send",
        method="POST",
        json_body={
            "threadId": provider_thread_id,
            "raw": encode_gmail_reply(
                to_address=to_address,
                subject=subject,
                body=body,
                internet_message_id=internet_message_id,
                references=references,
                message_id=message_id,
            ),
        },
        timeout=30,
    )
