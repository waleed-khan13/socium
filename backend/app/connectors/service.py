from __future__ import annotations

from typing import Any

from app.connector_store import (
    connector_runtime,
    primary_connector_runtime,
    record_connector_test,
)
from app.connectors.base import ConnectorTestResult
from app.connectors.registry import get_adapter
from app.errors import AppError
from app.services.slack import send_approval_message


async def test_saved_connector(account_id: str) -> ConnectorTestResult:
    try:
        runtime = connector_runtime(account_id)
    except RuntimeError as error:
        raise AppError("Saved connector secrets could not be decrypted.") from error
    if not runtime["enabled"]:
        raise AppError("Enable this connector before testing it.")
    adapter = get_adapter(str(runtime["adapter_id"]))
    try:
        result = await adapter.test_connection(runtime["config"], runtime["secrets"])
    except AppError as error:
        record_connector_test(account_id, ok=False, remote_account_id=None, message=error.message)
        raise
    record_connector_test(
        account_id,
        ok=result.ok,
        remote_account_id=result.remote_account_id,
        message=result.message,
    )
    return result


async def send_saved_slack_approval(
    post: dict[str, Any],
    approval_action_id: str,
) -> dict[str, str]:
    runtime = primary_connector_runtime("slack", verified_only=True)
    message_ts = await send_approval_message(
        str(runtime["secrets"].get("bot_token") or ""),
        str(runtime["config"].get("approval_channel_id") or ""),
        post,
        approval_action_id,
    )
    return {"accountId": str(runtime["id"]), "messageTs": message_ts}
