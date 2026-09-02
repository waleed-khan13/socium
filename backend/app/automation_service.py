from __future__ import annotations

from typing import Any

from app.errors import AppError
from app.services.content_package import generate_post_package
from app.services.telegram import send_approval_request
from app.store import (
    automation_runtime,
    create_approval_action,
    create_post,
    fail_approval_delivery,
    provider_runtime,
    record_approval_sent,
    telegram_runtime,
    workspace_runtime,
)


async def generate_automation_draft(
    automation_id: str,
    publish_at: str,
    *,
    send_slack_approval: Any,
) -> dict[str, Any]:
    rule = automation_runtime(automation_id)
    provider = provider_runtime()
    if not provider["base_url"] or not provider["model"]:
        raise AppError("Connect and verify an AI provider before this automation can run.")
    workspace = workspace_runtime()
    request = {
        "topic": rule["topic"],
        "channel": rule["channel"],
        "tone": rule["tone"],
        "objective": rule["objective"],
        "media_url": None,
    }
    generated = await generate_post_package(provider, request, workspace)
    request["media_asset_id"] = generated.media_asset_id
    post = create_post(
        request=request,
        content=generated.content.model_dump(),
        provider=provider,
        brand_profile_version=int(workspace.get("profile_version") or 0),
        automation_id=automation_id,
        automation_publish_at=publish_at,
    )

    channels = set(rule.get("approvalChannels") or [])
    warnings: list[str] = []
    if "telegram" in channels:
        telegram = telegram_runtime()
        if not telegram["bot_token"] or not telegram["chat_id"]:
            warnings.append("Telegram approval was not sent because Telegram is not connected.")
        else:
            approval = create_approval_action(post["id"], post["revision"], "telegram")
            try:
                message_id = await send_approval_request(
                    str(telegram["bot_token"]),
                    str(telegram["chat_id"]),
                    post,
                    approval["id"],
                    str(telegram.get("proxy_url") or ""),
                )
                record_approval_sent(approval["id"], message_id)
            except AppError as error:
                fail_approval_delivery(approval["id"], error.message)
                warnings.append(f"Telegram approval failed: {error.message}")

    if "slack" in channels:
        approval = create_approval_action(post["id"], post["revision"], "slack")
        try:
            delivery = await send_slack_approval(post, approval["id"])
            record_approval_sent(approval["id"], delivery["messageTs"])
        except AppError as error:
            fail_approval_delivery(approval["id"], error.message)
            warnings.append(f"Slack approval failed: {error.message}")
    return {"post": post, "warnings": warnings}
