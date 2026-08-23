from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

from app.errors import ExternalServiceError


async def slack_request(
    token: str,
    method: str,
    body: dict[str, Any] | None = None,
    *,
    timeout: float = 15,
) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=httpx.Timeout(timeout, connect=5.0),
        ) as client:
            response = await client.post(
                f"https://slack.com/api/{method}",
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json; charset=utf-8",
                },
                json=body or {},
            )
    except httpx.HTTPError as error:
        raise ExternalServiceError("Could not reach Slack from this computer.") from error

    try:
        payload = response.json()
    except ValueError as error:
        raise ExternalServiceError("Slack returned an unreadable response.") from error
    if not response.is_success or not isinstance(payload, dict) or not payload.get("ok"):
        reason = (
            str(payload.get("error") or f"HTTP {response.status_code}")
            if isinstance(payload, dict)
            else "invalid response"
        )
        raise ExternalServiceError(f"Slack {method} failed: {reason[:200]}.")
    return payload


async def open_socket_url(app_token: str) -> str:
    payload = await slack_request(app_token, "apps.connections.open", timeout=12)
    url = str(payload.get("url") or "")
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme != "wss" or not (hostname == "slack.com" or hostname.endswith(".slack.com")):
        raise ExternalServiceError("Slack returned an invalid Socket Mode URL.")
    return url


async def send_approval_message(
    bot_token: str,
    channel_id: str,
    post: dict[str, Any],
    approval_action_id: str,
) -> str:
    hashtag_line = f"\n\n{' '.join(post['hashtags'])}" if post.get("hashtags") else ""
    preview = f"{post['body']}{hashtag_line}"[:2_600]
    fallback = (
        f"Approval requested for {post['channel']} revision {post['revision']}: {post['title']}\n\n{preview}"
    )[:4_000]
    payload = await slack_request(
        bot_token,
        "chat.postMessage",
        {
            "channel": channel_id,
            "text": fallback,
            "mrkdwn": False,
            "unfurl_links": False,
            "unfurl_media": False,
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": "Socium approval requested"},
                },
                {
                    "type": "section",
                    "text": {
                        "type": "plain_text",
                        "text": f"{post['title']}\n\n{preview}"[:3_000],
                    },
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "plain_text",
                            "text": f"{post['channel']} · revision {post['revision']} · {post['id'][:8]}",
                        }
                    ],
                },
                {
                    "type": "actions",
                    "block_id": f"socium_approval_{post['id']}_{post['revision']}",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Approve"},
                            "style": "primary",
                            "action_id": "socium_approve",
                            "value": f"sa:a:{approval_action_id}",
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Regenerate"},
                            "action_id": "socium_regenerate",
                            "value": f"sa:r:{approval_action_id}",
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Edit in Socium"},
                            "action_id": "socium_edit",
                            "value": f"sa:e:{approval_action_id}",
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Skip"},
                            "style": "danger",
                            "action_id": "socium_skip",
                            "value": f"sa:s:{approval_action_id}",
                        },
                    ],
                },
            ],
        },
    )
    message_ts = payload.get("ts")
    if not isinstance(message_ts, str) or not message_ts:
        raise ExternalServiceError("Slack did not return a message timestamp.")
    return message_ts


async def send_decision_feedback(
    bot_token: str,
    channel_id: str,
    user_id: str,
    message: str,
) -> None:
    await slack_request(
        bot_token,
        "chat.postEphemeral",
        {
            "channel": channel_id,
            "user": user_id,
            "text": message[:2_000],
            "mrkdwn": False,
        },
    )
