from __future__ import annotations

from typing import Any

from app.connectors.base import ConnectorField, ConnectorManifest, ConnectorTestResult
from app.services.gmail import test_gmail_connection


class GmailAdapter:
    manifest = ConnectorManifest(
        adapter_id="gmail",
        name="Gmail",
        description="One-click email threads, approved AI replies, and local follow-up scheduling.",
        availability="available",
        capabilities=("inbox", "reply", "notification"),
        config_fields=(
            ConnectorField(
                key="email_address",
                label="Gmail address",
                required=True,
                placeholder="you@example.com",
                help_text="Filled automatically by Google OAuth.",
            ),
            ConnectorField(
                key="expires_at",
                label="Access expiry",
                required=True,
                placeholder="2026-09-07T12:00:00Z",
                help_text="Managed automatically by Socium.",
            ),
        ),
        secret_fields=(
            ConnectorField(
                key="access_token",
                label="OAuth access token",
                required=True,
                placeholder="Stored automatically",
                help_text="Encrypted in the local Socium vault.",
            ),
            ConnectorField(
                key="refresh_token",
                label="OAuth refresh token",
                required=True,
                placeholder="Stored automatically",
                help_text="Encrypted in the local Socium vault.",
            ),
        ),
        allowed_scopes=(
            "openid",
            "email",
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.send",
        ),
        required_scopes=(
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.send",
        ),
        docs_url="https://developers.google.com/workspace/gmail/api/guides",
    )

    async def test_connection(
        self,
        config: dict[str, Any],
        secrets: dict[str, str],
    ) -> ConnectorTestResult:
        details = await test_gmail_connection(secrets.get("access_token", ""))
        configured_email = str(config.get("email_address") or "").casefold()
        if configured_email and configured_email != details["emailAddress"].casefold():
            from app.errors import ExternalServiceError

            raise ExternalServiceError("Gmail token belongs to a different account.")
        return ConnectorTestResult(
            ok=True,
            message=f"Connected to Gmail as {details['emailAddress']}.",
            remote_account_id=details["emailAddress"],
            details=details,
        )
