from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path

import pytest


def test_slack_regeneration_acknowledges_before_waiting_for_ai(client, monkeypatch) -> None:
    from app.approval_actions import ApprovalActionResult
    from app.slack_listener import SlackInteractionResult, SlackSocketListener

    events: list[str] = []

    async def fake_feedback(
        _token: str,
        _channel: str,
        _user: str,
        message: str,
        **_relay: str,
    ) -> None:
        events.append(message)

    async def fake_apply(_action_id: str, _action: str, _source: str) -> ApprovalActionResult:
        events.append("AI generation")
        return ApprovalActionResult("Fresh revision is ready.", {"id": "post-1"})

    monkeypatch.setattr("app.slack_listener.send_decision_feedback", fake_feedback)
    monkeypatch.setattr("app.slack_listener.apply_remote_approval_action", fake_apply)

    listener = SlackSocketListener(enabled=False)
    asyncio.run(
        listener._apply_interaction(
            SlackInteractionResult(
                channel_id="D123",
                user_id="U123",
                message="",
                action_id="approval-1",
                action="regenerate",
            ),
            "xoxb-test",
            "D123",
            "account-1",
        )
    )

    assert events == [
        "Regeneration started. Socium is creating a fresh revision now.",
        "AI generation",
        "Fresh revision is ready.",
    ]


def test_storage_cache_is_scoped_to_the_selected_locations(client, monkeypatch, tmp_path: Path) -> None:
    from app import storage_health
    from app.config import get_settings

    first = replace(
        get_settings(),
        data_dir=tmp_path / "first-data",
        models_dir=tmp_path / "first-models",
    )
    second = replace(
        get_settings(),
        data_dir=tmp_path / "second-data",
        models_dir=tmp_path / "second-models",
    )
    calls: list[Path] = []

    def fake_build(settings):
        calls.append(settings.data_dir)
        return {"data": str(settings.data_dir)}

    monkeypatch.setattr(storage_health, "_build_storage_state", fake_build)
    monkeypatch.setattr(storage_health, "_cache", None)

    assert storage_health.storage_state(first)["data"].endswith("first-data")
    assert storage_health.storage_state(first)["data"].endswith("first-data")
    assert storage_health.storage_state(second)["data"].endswith("second-data")
    assert calls == [first.data_dir, second.data_dir]


def test_one_click_slack_health_uses_the_cloud_relay(client, monkeypatch) -> None:
    from app.config import get_settings
    from app.connectors.slack import SlackAdapter

    captured: dict[str, str] = {}

    async def fake_request(_token: str, method: str, **kwargs):
        captured.update({"method": method, **kwargs})
        return {"ok": True, "team_id": "T123", "team": "Socium"}

    relay_settings = replace(
        get_settings(),
        connect_broker_url="https://socium-connect.example",
    )
    monkeypatch.setattr("app.connectors.slack.get_settings", lambda: relay_settings)
    monkeypatch.setattr("app.connectors.slack.slack_request", fake_request)

    result = asyncio.run(
        SlackAdapter().test_connection(
            {"transport": "broker-relay", "approval_channel_id": "D123"},
            {
                "bot_token": "xoxb-valid-test-token",
                "relay_token": "r" * 48,
            },
        )
    )

    assert result.ok is True
    assert captured == {
        "method": "auth.test",
        "timeout": 12,
        "broker_url": "https://socium-connect.example",
        "relay_token": "r" * 48,
    }


def test_slack_relay_acknowledges_before_listener_goes_idle(client, monkeypatch) -> None:
    from app.slack_listener import SlackSocketListener

    listener = SlackSocketListener(enabled=True, broker_url="https://relay.example")
    events: list[str] = []

    class FakeResponse:
        is_success = True

        def __init__(self, payload: dict | None = None) -> None:
            self._payload = payload or {"ok": True}

        def json(self) -> dict:
            return self._payload

    class FakeClient:
        def __init__(self, **_kwargs) -> None:
            self.polls = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args) -> None:
            return None

        async def post(self, url: str, **_kwargs):
            if url.endswith("/actions/ack"):
                events.append("ack")
                assert listener._wake_event.is_set() is False
                return FakeResponse()
            self.polls += 1
            events.append("poll")
            if self.polls > 1:
                assert listener._wake_event.is_set() is True
                raise asyncio.CancelledError
            return FakeResponse(
                {
                    "ok": True,
                    "action": {
                        "id": "a" * 32,
                        "leaseToken": "l" * 32,
                        "payload": {
                            "type": "block_actions",
                            "channel": {"id": "D123"},
                            "user": {"id": "U123"},
                            "actions": [
                                {
                                    "action_id": "socium_approve",
                                    "value": "sa:a:approval-1",
                                }
                            ],
                        },
                    },
                }
            )

    async def fake_apply(*_args, **_kwargs) -> None:
        events.append("apply")

    monkeypatch.setattr("app.slack_listener.httpx.AsyncClient", FakeClient)
    monkeypatch.setattr(listener, "_apply_interaction", fake_apply)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            listener._listen_relay(
                {
                    "id": "account-1",
                    "secrets": {"relay_token": "r" * 48},
                },
                "xoxb-test",
                "D123",
            )
        )

    assert events == ["poll", "apply", "ack", "poll"]
