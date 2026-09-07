from __future__ import annotations

import base64
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from app.schemas import GeneratedEmailReply
from app.services.gmail import encode_gmail_reply, normalize_gmail_thread


def _gmail_payload() -> dict[str, Any]:
    body = base64.urlsafe_b64encode(b"Could you send the current pricing details?").decode()
    return {
        "id": "thread-gmail-v15",
        "historyId": "9001",
        "messages": [
            {
                "id": "message-gmail-v15",
                "internalDate": "1788739200000",
                "labelIds": ["INBOX", "UNREAD"],
                "snippet": "Could you send the current pricing details?",
                "payload": {
                    "mimeType": "text/plain",
                    "headers": [
                        {"name": "From", "value": "Buyer <buyer@example.com>"},
                        {"name": "To", "value": "owner@example.com"},
                        {"name": "Subject", "value": "Pricing request"},
                        {"name": "Message-ID", "value": "<provider-message@example.com>"},
                    ],
                    "body": {"data": body},
                },
            }
        ],
    }


def test_gmail_normalization_and_reply_headers_are_bounded() -> None:
    normalized = normalize_gmail_thread(_gmail_payload(), "owner@example.com")
    assert normalized["providerThreadId"] == "thread-gmail-v15"
    assert normalized["senderEmail"] == "buyer@example.com"
    assert normalized["classification"] == "needs_reply"
    assert normalized["unread"] is True

    raw = encode_gmail_reply(
        to_address="buyer@example.com\r\nBcc: attacker@example.com",
        subject="Pricing\r\nBcc: attacker@example.com",
        body="Approved body",
        internet_message_id="<provider-message@example.com>\r\nBcc: attacker@example.com",
        references="<older@example.com>\r\nBcc: attacker@example.com",
        message_id="<socium.test@example.local>",
    )
    decoded = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode()
    assert "\r\nBcc:" not in decoded
    assert "Approved body" in decoded
    assert "In-Reply-To: <provider-message@example.com>Bcc: attacker@example.com" in decoded


def test_gmail_sync_ai_approval_and_duplicate_safe_send(client, monkeypatch) -> None:
    from app import main
    from app import scheduler as scheduler_module

    created = client.post(
        "/api/connectors",
        json={
            "adapterId": "gmail",
            "name": "Gmail v1.5 test",
            "config": {"email_address": "owner@example.com", "expires_at": "2099-01-01T00:00:00Z"},
            "secrets": {"access_token": "test-access-token", "refresh_token": "test-refresh-token-long"},
            "scopes": [
                "openid",
                "email",
                "https://www.googleapis.com/auth/gmail.readonly",
                "https://www.googleapis.com/auth/gmail.send",
            ],
        },
    )
    assert created.status_code == 200
    account_id = created.json()["account"]["id"]

    async def fake_fetch(account: str, _limit: int):
        assert account == account_id
        return (
            {"config": {"email_address": "owner@example.com"}},
            [normalize_gmail_thread(_gmail_payload(), "owner@example.com")],
        )

    async def fake_generate(*_args, **_kwargs):
        return GeneratedEmailReply(
            subject="Re: Pricing request",
            body="Thanks for asking. Here are the confirmed details.",
            classification="sales",
            rationale="Uses the confirmed local business context.",
        )

    async def fake_send(*_args, **_kwargs):
        return {"id": "sent-gmail-v15"}

    monkeypatch.setattr(main, "fetch_gmail_threads", fake_fetch)
    monkeypatch.setattr(main, "send_gmail_reply", fake_send)
    monkeypatch.setattr(scheduler_module, "generate_email_reply", fake_generate)

    synced = client.post("/api/gmail/sync", json={"accountId": account_id, "limit": 5})
    assert synced.status_code == 200
    thread_id = next(
        item["id"]
        for item in synced.json()["items"]
        if item["providerThreadId"] == "thread-gmail-v15"
    )

    configured = client.put(
        "/api/settings/provider",
        json={
            "kind": "openai-compatible",
            "baseUrl": "https://provider.example/v1",
            "model": "email-test-model",
            "apiKey": "email-test-key",
        },
    )
    assert configured.status_code == 200

    queued = client.post(
        f"/api/email/threads/{thread_id}/reply-drafts",
        json={"instruction": "Answer the pricing question."},
    )
    assert queued.status_code == 202
    job_id = queued.json()["job"]["id"]
    job = None
    for _ in range(100):
        job = client.get(f"/api/email/jobs/{job_id}").json()["job"]
        if job["status"] in {"completed", "failed"}:
            break
        time.sleep(0.05)
    assert job is not None and job["status"] == "completed"

    thread = client.get(f"/api/email/threads/{thread_id}").json()["thread"]
    draft = thread["draft"]
    assert draft["status"] == "pending"
    assert draft["approvalRequestId"]

    approved = client.post(
        f"/api/approvals/{draft['approvalRequestId']}/decision",
        json={"action": "approve", "actor": "Test operator", "source": "dashboard"},
    )
    assert approved.status_code == 200
    scheduled = client.post(
        f"/api/email/reply-drafts/{draft['id']}/schedule",
        json={"runAt": (datetime.now(UTC) + timedelta(days=1)).isoformat()},
    )
    assert scheduled.status_code == 200
    scheduled_job_id = scheduled.json()["job"]["id"]
    sent = client.post(f"/api/email/reply-drafts/{draft['id']}/send")
    assert sent.status_code == 200
    assert sent.json()["draft"]["providerMessageId"] == "sent-gmail-v15"
    cancelled_schedule = client.get(f"/api/email/jobs/{scheduled_job_id}").json()["job"]
    assert cancelled_schedule["status"] == "cancelled"

    duplicate = client.post(f"/api/email/reply-drafts/{draft['id']}/send")
    assert duplicate.status_code == 409
