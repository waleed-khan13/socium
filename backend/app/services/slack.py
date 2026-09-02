from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

import httpx

from app.errors import ExternalServiceError
from app.media_store import media_asset_delivery


async def slack_request(
    token: str,
    method: str,
    body: dict[str, Any] | None = None,
    *,
    timeout: float = 15,
    broker_url: str = "",
    relay_token: str = "",
) -> dict[str, Any]:
    using_relay = bool(broker_url and relay_token)
    url = f"{broker_url.rstrip('/')}/v1/slack/api" if using_relay else f"https://slack.com/api/{method}"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json; charset=utf-8",
    }
    request_body: dict[str, Any] = body or {}
    if using_relay:
        request_body = {
            "relayToken": relay_token,
            "botToken": token,
            "method": method,
            "body": request_body,
        }
    else:
        headers["Authorization"] = f"Bearer {token}"
    try:
        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=httpx.Timeout(timeout, connect=5.0),
        ) as client:
            if not using_relay and method in {
                "files.getUploadURLExternal",
                "files.completeUploadExternal",
            }:
                headers["Content-Type"] = "application/x-www-form-urlencoded; charset=utf-8"
                form_body = {
                    key: json.dumps(value, separators=(",", ":"))
                    if isinstance(value, (dict, list))
                    else str(value)
                    for key, value in request_body.items()
                }
                response = await client.post(url, headers=headers, data=form_body)
            else:
                response = await client.post(url, headers=headers, json=request_body)
    except httpx.HTTPError as error:
        message = (
            "Could not reach Socium's Slack relay."
            if using_relay
            else "Could not reach Slack from this computer."
        )
        raise ExternalServiceError(message) from error

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
    if using_relay:
        result = payload.get("result")
        if not isinstance(result, dict) or not result.get("ok"):
            raise ExternalServiceError("Socium's Slack relay returned an invalid response.")
        return result
    return payload


async def open_socket_url(app_token: str) -> str:
    payload = await slack_request(app_token, "apps.connections.open", timeout=12)
    url = str(payload.get("url") or "")
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme != "wss" or not (hostname == "slack.com" or hostname.endswith(".slack.com")):
        raise ExternalServiceError("Slack returned an invalid Socket Mode URL.")
    return url


async def upload_approval_image(
    bot_token: str,
    media_asset_id: str,
    channel_id: str,
    *,
    broker_url: str = "",
    relay_token: str = "",
) -> str:
    media = media_asset_delivery(media_asset_id)
    prepared = await slack_request(
        bot_token,
        "files.getUploadURLExternal",
        {"filename": media["filename"], "length": media["byteSize"]},
        timeout=20,
        broker_url=broker_url,
        relay_token=relay_token,
    )
    upload_url = str(prepared.get("upload_url") or "")
    file_id = str(prepared.get("file_id") or "")
    parsed = urlparse(upload_url)
    hostname = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or not (hostname == "slack.com" or hostname.endswith(".slack.com"))
        or not file_id
    ):
        raise ExternalServiceError("Slack returned an invalid image upload destination.")
    try:
        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=httpx.Timeout(45, connect=8),
        ) as client:
            uploaded = await client.post(
                upload_url,
                content=media["data"],
                headers={"Content-Type": media["mimeType"]},
            )
    except httpx.HTTPError as error:
        raise ExternalServiceError("Could not upload the approval image to Slack.") from error
    if not uploaded.is_success:
        raise ExternalServiceError(f"Slack image upload failed with HTTP {uploaded.status_code}.")
    completed = await slack_request(
        bot_token,
        "files.completeUploadExternal",
        {
            "files": [{"id": file_id, "title": media["filename"]}],
            "channel_id": channel_id,
        },
        timeout=20,
        broker_url=broker_url,
        relay_token=relay_token,
    )
    files = completed.get("files")
    if not isinstance(files, list) or not files or str(files[0].get("id") or "") != file_id:
        raise ExternalServiceError("Slack did not confirm the uploaded approval image.")
    return file_id


async def send_approval_message(
    bot_token: str,
    channel_id: str,
    post: dict[str, Any],
    approval_action_id: str,
    *,
    broker_url: str = "",
    relay_token: str = "",
) -> str:
    hashtag_line = f"\n\n{' '.join(post['hashtags'])}" if post.get("hashtags") else ""
    preview = f"{post['body']}{hashtag_line}"[:2_600]
    fallback = (
        f"Approval requested for {post['channel']} revision {post['revision']}: {post['title']}\n\n{preview}"
    )[:4_000]
    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "Socium approval requested"},
        },
        {
            "type": "section",
            "text": {"type": "plain_text", "text": f"{post['title']}\n\n{preview}"[:3_000]},
        },
    ]
    media_asset_id = str(post.get("mediaAssetId") or "")
    if media_asset_id:
        slack_file_id = await upload_approval_image(
            bot_token,
            media_asset_id,
            channel_id,
            broker_url=broker_url,
            relay_token=relay_token,
        )
        blocks.append(
            {
                "type": "image",
                "slack_file": {"id": slack_file_id},
                "alt_text": str(
                    post.get("imageAltText") or post.get("title") or "Post image"
                )[:2_000],
            }
        )
    blocks.extend(
        [
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
                        "text": {"type": "plain_text", "text": "Regenerate post"},
                        "action_id": "socium_regenerate_post",
                        "value": f"sa:p:{approval_action_id}",
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Regenerate image"},
                        "action_id": "socium_regenerate_image",
                        "value": f"sa:i:{approval_action_id}",
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
        ]
    )
    payload = await slack_request(
        bot_token,
        "chat.postMessage",
        {
            "channel": channel_id,
            "text": fallback,
            "mrkdwn": False,
            "unfurl_links": False,
            "unfurl_media": False,
            "blocks": blocks,
        },
        broker_url=broker_url,
        relay_token=relay_token,
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
    *,
    broker_url: str = "",
    relay_token: str = "",
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
        broker_url=broker_url,
        relay_token=relay_token,
    )
