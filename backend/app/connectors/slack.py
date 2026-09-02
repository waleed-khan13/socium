from __future__ import annotations

from typing import Any

from app.config import get_settings
from app.connectors.base import ConnectorField, ConnectorManifest, ConnectorTestResult
from app.errors import ExternalServiceError
from app.services.slack import open_socket_url, slack_request


class SlackAdapter:
    manifest = ConnectorManifest(
        adapter_id="slack",
        name="Slack",
        description="Outbound Socket Mode approvals and notifications without a public webhook.",
        availability="available",
        capabilities=("approval", "notification"),
        config_fields=(
            ConnectorField(
                key="transport",
                label="Approval transport",
                required=False,
                placeholder="broker-relay",
                help_text="Managed automatically by Socium one-click setup.",
            ),
            ConnectorField(
                key="approval_channel_id",
                label="Approval channel ID",
                required=True,
                placeholder="C0123456789",
                help_text="The channel where Socium will send approval requests.",
            ),
        ),
        secret_fields=(
            ConnectorField(
                key="bot_token",
                label="Bot token",
                required=True,
                placeholder="xoxb-…",
                help_text="Slack bot token used for Web API calls.",
            ),
            ConnectorField(
                key="app_token",
                label="App-level token",
                required=False,
                placeholder="xapp-…",
                help_text="Socket Mode app token with connections:write.",
            ),
            ConnectorField(
                key="relay_token",
                label="Managed relay token",
                required=False,
                placeholder="Stored by one-click setup",
                help_text="One-time OAuth relay credential stored only in the local encrypted vault.",
            ),
        ),
        allowed_scopes=("chat:write", "im:write", "connections:write", "files:write"),
        required_scopes=("chat:write", "files:write"),
        docs_url="https://docs.slack.dev/tools/python-slack-sdk/socket-mode/",
    )

    async def test_connection(
        self,
        config: dict[str, Any],
        secrets: dict[str, str],
    ) -> ConnectorTestResult:
        bot_token = secrets.get("bot_token", "")
        app_token = secrets.get("app_token", "")
        relay_token = secrets.get("relay_token", "")
        transport = str(config.get("transport") or "socket-mode")
        if not bot_token.startswith("xoxb-"):
            raise ExternalServiceError("Slack bot token must start with xoxb-.")
        if transport == "broker-relay":
            if len(relay_token) < 32:
                raise ExternalServiceError("Slack one-click relay credential is missing.")
            if not get_settings().connect_broker_url:
                raise ExternalServiceError("Socium's one-click connection service is not configured.")
        elif not app_token.startswith("xapp-"):
            raise ExternalServiceError("Slack app-level token must start with xapp-.")
        if not str(config.get("approval_channel_id") or "").strip():
            raise ExternalServiceError("Slack approval channel ID is required.")

        auth_payload = await slack_request(
            bot_token,
            "auth.test",
            timeout=12,
            broker_url=get_settings().connect_broker_url if transport == "broker-relay" else "",
            relay_token=relay_token if transport == "broker-relay" else "",
        )
        if transport != "broker-relay":
            await open_socket_url(app_token)

        team_id = str(auth_payload.get("team_id") or "")
        return ConnectorTestResult(
            ok=True,
            message=f"Connected to Slack workspace {auth_payload.get('team') or team_id}.",
            remote_account_id=team_id or None,
            details={
                "team": str(auth_payload.get("team") or ""),
                "botUserId": str(auth_payload.get("user_id") or ""),
                "transport": transport,
            },
        )
