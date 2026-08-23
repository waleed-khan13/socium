from __future__ import annotations

from typing import Any

import httpx

from app.errors import ExternalServiceError


async def telegram_request(
    token: str,
    method: str,
    body: dict[str, Any] | None = None,
    *,
    timeout: float = 35,
) -> Any:
    try:
        async with httpx.AsyncClient(follow_redirects=False, timeout=timeout) as client:
            response = await client.request(
                "POST" if body is not None else "GET",
                f"https://api.telegram.org/bot{token}/{method}",
                json=body,
                headers={"Accept": "application/json"},
            )
    except httpx.HTTPError as error:
        raise ExternalServiceError(f"Telegram request failed ({type(error).__name__}).") from error
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


async def test_connection(token: str) -> dict[str, Any]:
    bot = await telegram_request(token, "getMe")
    if not isinstance(bot, dict):
        raise ExternalServiceError("Telegram returned an invalid bot profile.")
    return {
        "id": bot.get("id"),
        "name": f"@{bot['username']}"
        if bot.get("username")
        else str(bot.get("first_name") or "Telegram bot"),
    }


async def delete_webhook(token: str) -> None:
    await telegram_request(token, "deleteWebhook", {"drop_pending_updates": False})


async def get_updates(token: str, offset: int, poll_timeout: int) -> list[dict[str, Any]]:
    result = await telegram_request(
        token,
        "getUpdates",
        {
            "offset": offset,
            "timeout": poll_timeout,
            "allowed_updates": ["callback_query"],
        },
        timeout=poll_timeout + 10,
    )
    return [item for item in result if isinstance(item, dict)] if isinstance(result, list) else []


async def send_approval_request(
    token: str,
    chat_id: str,
    post: dict[str, Any],
    action_id: str,
) -> str:
    hashtag_line = f"\n\n{' '.join(post['hashtags'])}" if post.get("hashtags") else ""
    preview = f"{post['body']}{hashtag_line}"[:3_000]
    result = await telegram_request(
        token,
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": f"Approval requested · {post['channel']} · revision {post['revision']}\n\n{post['title']}\n\n{preview}",
            "reply_markup": {
                "inline_keyboard": [
                    [
                        {
                            "text": "Approve",
                            "callback_data": f"sa:a:{action_id}",
                        },
                        {
                            "text": "Regenerate",
                            "callback_data": f"sa:r:{action_id}",
                        },
                    ],
                    [
                        {
                            "text": "Edit in Socium",
                            "callback_data": f"sa:e:{action_id}",
                        },
                        {
                            "text": "Skip",
                            "callback_data": f"sa:s:{action_id}",
                        },
                    ]
                ]
            },
        },
    )
    if not isinstance(result, dict) or result.get("message_id") is None:
        raise ExternalServiceError("Telegram did not return an approval message ID.")
    return str(result["message_id"])


async def publish_post(token: str, chat_id: str, post: dict[str, Any]) -> str:
    hashtag_line = f"\n\n{' '.join(post['hashtags'])}" if post.get("hashtags") else ""
    result = await telegram_request(
        token,
        "sendMessage",
        {"chat_id": chat_id, "text": f"{post['body']}{hashtag_line}"[:4_096]},
    )
    if not isinstance(result, dict) or result.get("message_id") is None:
        raise ExternalServiceError("Telegram did not return a message ID.")
    return str(result["message_id"])


async def answer_callback(token: str, callback_id: str, text: str) -> None:
    await telegram_request(
        token,
        "answerCallbackQuery",
        {"callback_query_id": callback_id, "text": text[:200]},
    )


async def send_status_message(token: str, chat_id: str, text: str) -> None:
    await telegram_request(
        token,
        "sendMessage",
        {"chat_id": chat_id, "text": text[:4_096]},
    )
