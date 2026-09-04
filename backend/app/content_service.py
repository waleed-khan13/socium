from __future__ import annotations

from collections.abc import Callable
from time import perf_counter
from typing import Any

from app.business_os_store import record_ai_decision
from app.connectors.service import send_saved_slack_approval
from app.errors import AppError
from app.services.content_package import generate_post_package
from app.services.telegram import send_approval_request
from app.store import (
    create_approval_action,
    create_post,
    fail_approval_delivery,
    provider_runtime,
    record_approval_sent,
    telegram_runtime,
    workspace_runtime,
)

ProgressCallback = Callable[[int, str], None]


def _progress(callback: ProgressCallback | None, percent: int, message: str) -> None:
    if callback is not None:
        callback(percent, message)


async def generate_content_draft(
    request_data: dict[str, Any],
    *,
    progress: ProgressCallback | None = None,
    approval_wake: Callable[[], None] | None = None,
) -> dict[str, Any]:
    provider = provider_runtime()
    if not provider["base_url"] or not provider["model"]:
        raise AppError("Connect an AI provider and select a model first.")
    workspace = workspace_runtime()
    started = perf_counter()
    _progress(progress, 12, "Preparing confirmed business context.")
    try:
        generated = await generate_post_package(provider, request_data, workspace)
    except Exception as error:
        message = error.message if isinstance(error, AppError) else str(error) or "Generation failed."
        record_ai_decision(
            purpose="content.generate",
            provider_kind=str(provider["kind"]),
            model=str(provider["model"]),
            status="failed",
            duration_ms=round((perf_counter() - started) * 1_000),
            context_refs=[
                {"type": "business_profile", "revision": workspace.get("profile_version", 0)},
                {"type": "confirmed_knowledge", "count": len(workspace.get("confirmed_knowledge") or [])},
            ],
            error=message,
        )
        raise

    _progress(progress, 78, "Content kit generated; saving its exact revision.")
    record_ai_decision(
        purpose="content.generate",
        provider_kind=str(provider["kind"]),
        model=str(provider["model"]),
        status="completed",
        duration_ms=round((perf_counter() - started) * 1_000),
        context_refs=[
            {"type": "business_profile", "revision": workspace.get("profile_version", 0)},
            {"type": "confirmed_knowledge", "count": len(workspace.get("confirmed_knowledge") or [])},
        ],
    )
    request_data["media_asset_id"] = generated.media_asset_id
    post = create_post(
        request=request_data,
        content=generated.content.model_dump(),
        provider=provider,
        brand_profile_version=int(workspace.get("profile_version") or 0),
    )

    _progress(progress, 88, "Draft saved; delivering requested approval notifications.")
    notifications: list[dict[str, Any]] = []
    if request_data.get("notify_telegram"):
        try:
            telegram = telegram_runtime()
            if not telegram["bot_token"] or not telegram["chat_id"]:
                raise AppError("Telegram approval is not configured.")
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
                raise
            notifications.append(
                {"channel": "telegram", "ok": True, "message": "Approval request sent to Telegram."}
            )
        except AppError as error:
            notifications.append({"channel": "telegram", "ok": False, "message": error.message})

    if request_data.get("notify_slack"):
        try:
            approval = create_approval_action(post["id"], post["revision"], "slack")
            try:
                delivery = await send_saved_slack_approval(post, approval["id"])
                record_approval_sent(approval["id"], delivery["messageTs"])
            except AppError as error:
                fail_approval_delivery(approval["id"], error.message)
                raise
            notifications.append(
                {"channel": "slack", "ok": True, "message": "Approval request sent to Slack."}
            )
        except AppError as error:
            notifications.append({"channel": "slack", "ok": False, "message": error.message})

    if approval_wake is not None and any(item["ok"] for item in notifications):
        approval_wake()
    _progress(progress, 96, "Finalizing the local content job.")
    return {"post": post, "notifications": notifications}
