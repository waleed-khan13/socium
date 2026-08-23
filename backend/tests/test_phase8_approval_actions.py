from __future__ import annotations

import asyncio
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest


def _configure_provider(client) -> None:
    response = client.put(
        "/api/settings/provider",
        json={
            "kind": "openai-compatible",
            "baseUrl": "https://provider.example/v1",
            "model": "approval-test-model",
            "apiKey": "approval-test-key",
        },
    )
    assert response.status_code == 200


def _generate(client, topic: str) -> dict:
    response = client.post(
        "/api/posts/generate",
        json={
            "topic": topic,
            "channel": "linkedin",
            "tone": "Clear",
            "objective": "Exercise the approval contract",
            "notifyTelegram": False,
            "notifySlack": False,
        },
    )
    assert response.status_code == 200
    return response.json()["post"]


@pytest.fixture
def generated_content(monkeypatch):
    from app.schemas import GeneratedContent

    sequence = 0

    async def fake_generate(*_args, **_kwargs):
        nonlocal sequence
        sequence += 1
        return GeneratedContent(
            title=f"Approval revision {sequence}",
            body=f"Reviewed content version {sequence}.",
            hashtags=["#Socium", f"#Revision{sequence}"],
            call_to_action="Review the local workflow.",
            image_prompt=f"A local approval workspace, variation {sequence}",
            image_negative_prompt="watermark",
            image_alt_text=f"Local approval workspace variation {sequence}",
            rationale="Exercises exact-revision approval behavior.",
        )

    monkeypatch.setattr("app.main.generate_content", fake_generate)
    monkeypatch.setattr("app.approval_actions.generate_content", fake_generate)
    return fake_generate


def test_dashboard_actions_are_exact_revision_bound(client, generated_content) -> None:
    _configure_provider(client)
    post = _generate(client, "Dashboard phase eight")

    regenerated = client.post(
        f"/api/posts/{post['id']}/regenerate",
        json={"revision": post["revision"]},
    )
    assert regenerated.status_code == 200
    revision_two = regenerated.json()["post"]
    assert revision_two["revision"] == 2
    assert revision_two["status"] == "pending"
    assert revision_two["title"] != post["title"]

    stale_regenerate = client.post(
        f"/api/posts/{post['id']}/regenerate",
        json={"revision": 1},
    )
    assert stale_regenerate.status_code == 400

    stale_edit = client.patch(
        f"/api/posts/{post['id']}",
        json={
            "revision": 1,
            "title": "Stale overwrite",
            "body": "This must not replace revision two.",
            "hashtags": [],
        },
    )
    assert stale_edit.status_code == 400

    skipped = client.post(
        f"/api/posts/{post['id']}/decision",
        json={"decision": "skip", "revision": 2},
    )
    assert skipped.status_code == 200
    final_post = next(
        item for item in skipped.json()["state"]["posts"] if item["id"] == post["id"]
    )
    assert final_post["status"] == "skipped"
    assert final_post["approvedAt"] is None

    repeated = client.post(
        f"/api/posts/{post['id']}/decision",
        json={"decision": "skip", "revision": 2},
    )
    assert repeated.status_code == 400
    assert any(
        event["action"] == "post.skipped" and event["entityId"] == post["id"]
        for event in skipped.json()["state"]["audit"]
    )


def test_telegram_and_slack_render_all_revision_actions(monkeypatch) -> None:
    telegram_payload: dict = {}
    slack_payload: dict = {}

    async def fake_telegram(_token: str, method: str, body: dict, **_kwargs):
        assert method == "sendMessage"
        telegram_payload.update(body)
        return {"message_id": 42}

    async def fake_slack(_token: str, method: str, body: dict, **_kwargs):
        assert method == "chat.postMessage"
        slack_payload.update(body)
        return {"ok": True, "ts": "1712345678.000300"}

    monkeypatch.setattr("app.services.telegram.telegram_request", fake_telegram)
    monkeypatch.setattr("app.services.slack.slack_request", fake_slack)
    from app.services.slack import send_approval_message
    from app.services.telegram import send_approval_request

    post = {
        "id": "post-phase-eight",
        "revision": 9,
        "channel": "linkedin",
        "title": "Four safe actions",
        "body": "Review this exact revision.",
        "hashtags": ["#Socium"],
    }
    action_id = "12345678-1234-1234-1234-123456789012"
    message_id = asyncio.run(send_approval_request("token", "12345", post, action_id))
    message_ts = asyncio.run(send_approval_message("token", "C123", post, action_id))
    assert message_id == "42"
    assert message_ts == "1712345678.000300"

    telegram_buttons = [
        button
        for row in telegram_payload["reply_markup"]["inline_keyboard"]
        for button in row
    ]
    assert [button["text"] for button in telegram_buttons] == [
        "Approve",
        "Regenerate",
        "Edit in Socium",
        "Skip",
    ]
    assert all(len(button["callback_data"].encode()) <= 64 for button in telegram_buttons)
    assert [button["callback_data"] for button in telegram_buttons] == [
        f"sa:a:{action_id}",
        f"sa:r:{action_id}",
        f"sa:e:{action_id}",
        f"sa:s:{action_id}",
    ]

    slack_buttons = slack_payload["blocks"][-1]["elements"]
    assert [button["action_id"] for button in slack_buttons] == [
        "socium_approve",
        "socium_regenerate",
        "socium_edit",
        "socium_skip",
    ]


def test_remote_actions_are_durable_expiring_and_replay_protected(
    client,
    generated_content,
) -> None:
    from app.approval_actions import apply_remote_approval_action
    from app.config import get_settings
    from app.errors import AppError
    from app.store import (
        claim_remote_approval_action,
        create_approval_action,
        initialize_storage,
        process_telegram_update,
        record_approval_sent,
    )

    _configure_provider(client)
    edit_post = _generate(client, "Remote edit handoff")
    edit_action = create_approval_action(edit_post["id"], edit_post["revision"], "telegram")
    record_approval_sent(edit_action["id"], "telegram-message-1")

    with pytest.raises(AppError, match="mismatched"):
        asyncio.run(apply_remote_approval_action(edit_action["id"], "edit", "slack"))

    edited = asyncio.run(apply_remote_approval_action(edit_action["id"], "edit", "telegram"))
    assert edited.post["revision"] == 1
    state_after_restart = client.get("/api/state").json()
    assert state_after_restart["remoteEditRequest"] == {
        "id": edit_action["id"],
        "postId": edit_post["id"],
        "revision": 1,
        "source": "telegram",
        "createdAt": state_after_restart["remoteEditRequest"]["createdAt"],
    }
    with pytest.raises(AppError, match="already used"):
        asyncio.run(apply_remote_approval_action(edit_action["id"], "edit", "telegram"))
    acknowledged = client.post(f"/api/approval-actions/{edit_action['id']}/edit/ack")
    assert acknowledged.status_code == 200
    assert client.get("/api/state").json()["remoteEditRequest"] is None

    regenerate_post = _generate(client, "Remote regenerate")
    regenerate_action = create_approval_action(
        regenerate_post["id"], regenerate_post["revision"], "slack"
    )
    record_approval_sent(regenerate_action["id"], "slack-message-1")
    regenerated = asyncio.run(
        apply_remote_approval_action(regenerate_action["id"], "regenerate", "slack")
    )
    assert regenerated.regenerated is True
    assert regenerated.post["revision"] == 2
    assert regenerated.post["status"] == "pending"
    with pytest.raises(AppError, match="already used"):
        asyncio.run(
            apply_remote_approval_action(regenerate_action["id"], "regenerate", "slack")
        )

    expired_post = _generate(client, "Expired remote action")
    expired_action = create_approval_action(expired_post["id"], 1, "telegram")
    record_approval_sent(expired_action["id"], "telegram-message-expired")
    expired_at = (datetime.now(UTC) - timedelta(minutes=1)).isoformat().replace("+00:00", "Z")
    with sqlite3.connect(get_settings().database_path) as connection:
        connection.execute(
            "UPDATE approval_actions SET expires_at = ? WHERE id = ?",
            (expired_at, expired_action["id"]),
        )
    with pytest.raises(AppError, match="expired"):
        asyncio.run(apply_remote_approval_action(expired_action["id"], "approve", "telegram"))
    with sqlite3.connect(get_settings().database_path) as connection:
        status = connection.execute(
            "SELECT status FROM approval_actions WHERE id = ?",
            (expired_action["id"],),
        ).fetchone()
    assert status == ("expired",)

    telegram_skip_post = _generate(client, "Telegram skip action")
    telegram_skip = create_approval_action(telegram_skip_post["id"], 1, "telegram")
    record_approval_sent(telegram_skip["id"], "telegram-message-skip")
    client.put(
        "/api/settings/telegram",
        json={"chatId": "12345", "botToken": "123456:phase-eight-token"},
    )
    parsed = process_telegram_update(
        {
            "update_id": 2_000_000_001,
            "callback_query": {
                "id": "callback-phase-eight",
                "data": f"sa:s:{telegram_skip['id']}",
                "message": {"chat": {"id": 12345}},
            },
        }
    )
    assert parsed == {
        "callbackId": "callback-phase-eight",
        "actionId": telegram_skip["id"],
        "action": "skip",
    }
    skipped = asyncio.run(
        apply_remote_approval_action(parsed["actionId"], parsed["action"], "telegram")  # type: ignore[arg-type]
    )
    assert skipped.post["status"] == "skipped"
    assert process_telegram_update(
        {
            "update_id": 2_000_000_001,
            "callback_query": {
                "id": "callback-phase-eight-replay",
                "data": f"sa:s:{telegram_skip['id']}",
            },
        }
    ) is None

    interrupted_post = _generate(client, "Restart recovery")
    interrupted_action = create_approval_action(interrupted_post["id"], 1, "slack")
    record_approval_sent(interrupted_action["id"], "slack-message-interrupted")
    claim_remote_approval_action(interrupted_action["id"], "regenerate", "slack")
    initialize_storage()
    with sqlite3.connect(get_settings().database_path) as connection:
        recovered = connection.execute(
            "SELECT status, last_error FROM approval_actions WHERE id = ?",
            (interrupted_action["id"],),
        ).fetchone()
    assert recovered is not None
    assert recovered[0] == "failed"
    assert "restarted" in recovered[1]
