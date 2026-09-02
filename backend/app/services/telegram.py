from __future__ import annotations

import json
from typing import Any

import httpx

from app.errors import ExternalServiceError
from app.media_store import media_asset_delivery


def validate_proxy_url(value: str) -> str:
    proxy_url = value.strip()
    if not proxy_url:
        return ""
    try:
        parsed = httpx.URL(proxy_url)
    except Exception as error:
        raise ExternalServiceError("Telegram proxy URL is invalid.") from error
    if parsed.scheme not in {"http", "https", "socks5", "socks5h"} or not parsed.host:
        raise ExternalServiceError("Use an HTTP, HTTPS, SOCKS5, or SOCKS5H Telegram proxy URL.")
    return str(parsed)


def _telegram_network_error(error: httpx.HTTPError, *, using_proxy: bool) -> ExternalServiceError:
    if using_proxy:
        if isinstance(error, httpx.ProxyError):
            return ExternalServiceError(
                "The Telegram proxy rejected the connection. Check its address, port, username, and password."
            )
        if isinstance(error, (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout)):
            return ExternalServiceError(
                "The Telegram proxy timed out. Check that the proxy is online and allows HTTPS connections."
            )
        return ExternalServiceError(
            "Could not reach Telegram through this proxy. Check the proxy address and whether it supports HTTPS tunnelling."
        )
    return ExternalServiceError(f"Telegram request failed ({type(error).__name__}).")


async def test_proxy_connection(proxy_url: str) -> None:
    normalized = validate_proxy_url(proxy_url)
    if not normalized:
        raise ExternalServiceError("Enter an HTTP or SOCKS5 proxy URL first.")
    try:
        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=httpx.Timeout(10, connect=7),
            proxy=normalized,
        ) as client:
            response = await client.get(
                "https://api.telegram.org/",
                headers={"Accept": "text/html,application/json"},
            )
    except httpx.HTTPError as error:
        raise _telegram_network_error(error, using_proxy=True) from error
    if response.status_code == 407:
        raise ExternalServiceError("The Telegram proxy requires valid authentication credentials.")
    if response.status_code >= 500:
        raise ExternalServiceError(
            f"The proxy reached Telegram but received HTTP {response.status_code}. Try again shortly."
        )


async def telegram_request(
    token: str,
    method: str,
    body: dict[str, Any] | None = None,
    *,
    timeout: float = 35,
    proxy_url: str = "",
) -> Any:
    try:
        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=timeout,
            proxy=validate_proxy_url(proxy_url) or None,
        ) as client:
            response = await client.request(
                "POST" if body is not None else "GET",
                f"https://api.telegram.org/bot{token}/{method}",
                json=body,
                headers={"Accept": "application/json"},
            )
    except httpx.HTTPError as error:
        raise _telegram_network_error(error, using_proxy=bool(proxy_url.strip())) from error
    try:
        payload = response.json()
    except ValueError as error:
        raise ExternalServiceError(
            f"Telegram returned a non-JSON response ({response.status_code})."
        ) from error
    if not response.is_success or not isinstance(payload, dict) or not payload.get("ok"):
        description = str(payload.get("description") or "") if isinstance(payload, dict) else ""
        raise ExternalServiceError(description or f"Telegram returned HTTP {response.status_code}.")
    return payload.get("result")


async def telegram_upload_request(
    token: str,
    method: str,
    fields: dict[str, str],
    *,
    filename: str,
    data: bytes,
    mime_type: str,
    timeout: float = 45,
    proxy_url: str = "",
) -> Any:
    try:
        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=timeout,
            proxy=validate_proxy_url(proxy_url) or None,
        ) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{token}/{method}",
                data=fields,
                files={"photo": (filename, data, mime_type)},
                headers={"Accept": "application/json"},
            )
    except httpx.HTTPError as error:
        raise _telegram_network_error(error, using_proxy=bool(proxy_url.strip())) from error
    try:
        payload = response.json()
    except ValueError as error:
        raise ExternalServiceError(
            f"Telegram returned a non-JSON response ({response.status_code})."
        ) from error
    if not response.is_success or not isinstance(payload, dict) or not payload.get("ok"):
        description = str(payload.get("description") or "") if isinstance(payload, dict) else ""
        raise ExternalServiceError(description or f"Telegram returned HTTP {response.status_code}.")
    return payload.get("result")


async def test_connection(token: str, proxy_url: str = "") -> dict[str, Any]:
    bot = await telegram_request(token, "getMe", proxy_url=proxy_url)
    if not isinstance(bot, dict):
        raise ExternalServiceError("Telegram returned an invalid bot profile.")
    return {
        "id": bot.get("id"),
        "name": f"@{bot['username']}"
        if bot.get("username")
        else str(bot.get("first_name") or "Telegram bot"),
    }


async def delete_webhook(token: str, proxy_url: str = "") -> None:
    await telegram_request(
        token,
        "deleteWebhook",
        {"drop_pending_updates": False},
        proxy_url=proxy_url,
    )


async def resolve_chat(token: str, chat_id: str, proxy_url: str = "") -> dict[str, str]:
    chat = await telegram_request(token, "getChat", {"chat_id": chat_id}, proxy_url=proxy_url)
    if not isinstance(chat, dict) or chat.get("id") is None:
        raise ExternalServiceError("Telegram returned an invalid approval chat.")
    label = (
        chat.get("title")
        or " ".join(
            value
            for value in (chat.get("first_name"), chat.get("last_name"))
            if isinstance(value, str) and value.strip()
        )
        or chat.get("username")
        or str(chat["id"])
    )
    return {
        "chatId": str(chat["id"]),
        "chatType": str(chat.get("type") or "unknown"),
        "chatLabel": str(label)[:160],
    }


async def discover_recent_chat(token: str, proxy_url: str = "") -> dict[str, Any] | None:
    result = await telegram_request(
        token,
        "getUpdates",
        {
            "offset": -1,
            "timeout": 0,
            "allowed_updates": ["message", "channel_post", "my_chat_member"],
        },
        proxy_url=proxy_url,
    )
    if not isinstance(result, list):
        return None
    candidates: list[dict[str, Any]] = []
    for update in result:
        if not isinstance(update, dict):
            continue
        event = next(
            (
                update.get(key)
                for key in ("message", "channel_post", "my_chat_member")
                if isinstance(update.get(key), dict)
            ),
            None,
        )
        chat = event.get("chat") if isinstance(event, dict) else None
        if not isinstance(chat, dict) or chat.get("id") is None:
            continue
        sender = event.get("from") if isinstance(event.get("from"), dict) else {}
        label = (
            chat.get("title")
            or " ".join(
                value
                for value in (sender.get("first_name"), sender.get("last_name"))
                if isinstance(value, str) and value.strip()
            )
            or sender.get("username")
            or str(chat.get("id"))
        )
        text = str(event.get("text") or "")
        candidates.append(
            {
                "chatId": str(chat["id"]),
                "chatType": str(chat.get("type") or "unknown"),
                "chatLabel": str(label)[:160],
                "updateId": max(int(update.get("update_id") or 0), 0),
                "started": text.casefold().startswith("/start"),
            }
        )
    if not candidates:
        return None
    return next((candidate for candidate in reversed(candidates) if candidate["started"]), None)


async def get_updates(
    token: str,
    offset: int,
    poll_timeout: int,
    proxy_url: str = "",
) -> list[dict[str, Any]]:
    result = await telegram_request(
        token,
        "getUpdates",
        {
            "offset": offset,
            "timeout": poll_timeout,
            "allowed_updates": ["callback_query"],
        },
        timeout=poll_timeout + 10,
        proxy_url=proxy_url,
    )
    return [item for item in result if isinstance(item, dict)] if isinstance(result, list) else []


async def send_approval_request(
    token: str,
    chat_id: str,
    post: dict[str, Any],
    action_id: str,
    proxy_url: str = "",
) -> str:
    hashtag_line = f"\n\n{' '.join(post['hashtags'])}" if post.get("hashtags") else ""
    keyboard = {
        "inline_keyboard": [
            [{"text": "Approve", "callback_data": f"sa:a:{action_id}"}],
            [
                {"text": "Regenerate post", "callback_data": f"sa:p:{action_id}"},
                {"text": "Regenerate image", "callback_data": f"sa:i:{action_id}"},
            ],
            [
                {"text": "Edit in Socium", "callback_data": f"sa:e:{action_id}"},
                {"text": "Skip", "callback_data": f"sa:s:{action_id}"},
            ],
        ]
    }
    heading = f"Approval requested · {post['channel']} · revision {post['revision']}"
    full_text = f"{heading}\n\n{post['title']}\n\n{post['body']}{hashtag_line}"
    media_asset_id = str(post.get("mediaAssetId") or "")
    if media_asset_id:
        media = media_asset_delivery(media_asset_id)
        result = await telegram_upload_request(
            token,
            "sendPhoto",
            {
                "chat_id": chat_id,
                "caption": full_text[:1_024],
                "reply_markup": json.dumps(keyboard, separators=(",", ":")),
            },
            filename=media["filename"],
            data=media["data"],
            mime_type=media["mimeType"],
            proxy_url=proxy_url,
        )
    else:
        result = await telegram_request(
            token,
            "sendMessage",
            {"chat_id": chat_id, "text": full_text[:4_096], "reply_markup": keyboard},
            proxy_url=proxy_url,
        )
    if not isinstance(result, dict) or result.get("message_id") is None:
        raise ExternalServiceError("Telegram did not return an approval message ID.")
    return str(result["message_id"])


async def publish_post(
    token: str,
    chat_id: str,
    post: dict[str, Any],
    proxy_url: str = "",
) -> str:
    hashtag_line = f"\n\n{' '.join(post['hashtags'])}" if post.get("hashtags") else ""
    text = f"{post['body']}{hashtag_line}"
    media_asset_id = str(post.get("mediaAssetId") or "")
    if media_asset_id:
        media = media_asset_delivery(media_asset_id)
        result = await telegram_upload_request(
            token,
            "sendPhoto",
            {"chat_id": chat_id, "caption": text[:1_024]},
            filename=media["filename"],
            data=media["data"],
            mime_type=media["mimeType"],
            proxy_url=proxy_url,
        )
    else:
        result = await telegram_request(
            token,
            "sendMessage",
            {"chat_id": chat_id, "text": text[:4_096]},
            proxy_url=proxy_url,
        )
    if not isinstance(result, dict) or result.get("message_id") is None:
        raise ExternalServiceError("Telegram did not return a message ID.")
    return str(result["message_id"])


async def answer_callback(token: str, callback_id: str, text: str, proxy_url: str = "") -> None:
    await telegram_request(
        token,
        "answerCallbackQuery",
        {"callback_query_id": callback_id, "text": text[:200]},
        proxy_url=proxy_url,
    )


async def update_approval_message(
    token: str,
    chat_id: str,
    message_id: str,
    original_text: str,
    status: str,
    proxy_url: str = "",
    has_photo: bool = False,
) -> None:
    suffix = f"\n\nSOCIUM STATUS: {status}"
    available = max(0, (1_024 if has_photo else 4_096) - len(suffix))
    text = f"{original_text[:available].rstrip()}{suffix}"
    await telegram_request(
        token,
        "editMessageCaption" if has_photo else "editMessageText",
        {
            "chat_id": chat_id,
            "message_id": int(message_id),
            "caption" if has_photo else "text": text,
            "reply_markup": {"inline_keyboard": []},
        },
        proxy_url=proxy_url,
    )


async def send_status_message(
    token: str,
    chat_id: str,
    text: str,
    proxy_url: str = "",
) -> None:
    await telegram_request(
        token,
        "sendMessage",
        {"chat_id": chat_id, "text": text[:4_096]},
        proxy_url=proxy_url,
    )
