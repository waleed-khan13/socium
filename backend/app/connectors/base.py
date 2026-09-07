from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol

ConnectorCapability = Literal[
    "approval",
    "notification",
    "publish",
    "leads",
    "analytics",
    "cms",
    "inbox",
    "reply",
]
ConnectorAvailability = Literal["available", "planned", "access-gated", "notification-only", "built-in"]


@dataclass(frozen=True, slots=True)
class ConnectorField:
    key: str
    label: str
    required: bool
    placeholder: str = ""
    help_text: str = ""

    def public_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "required": self.required,
            "placeholder": self.placeholder,
            "helpText": self.help_text,
        }


@dataclass(frozen=True, slots=True)
class ConnectorManifest:
    adapter_id: str
    name: str
    description: str
    availability: ConnectorAvailability
    capabilities: tuple[ConnectorCapability, ...]
    config_fields: tuple[ConnectorField, ...] = ()
    secret_fields: tuple[ConnectorField, ...] = ()
    allowed_scopes: tuple[str, ...] = ()
    required_scopes: tuple[str, ...] = ()
    docs_url: str | None = None

    def public_dict(self) -> dict[str, Any]:
        return {
            "adapterId": self.adapter_id,
            "name": self.name,
            "description": self.description,
            "availability": self.availability,
            "capabilities": list(self.capabilities),
            "configFields": [field.public_dict() for field in self.config_fields],
            "secretFields": [field.public_dict() for field in self.secret_fields],
            "allowedScopes": list(self.allowed_scopes),
            "requiredScopes": list(self.required_scopes),
            "docsUrl": self.docs_url,
        }


@dataclass(frozen=True, slots=True)
class ConnectorTestResult:
    ok: bool
    message: str
    remote_account_id: str | None = None
    details: dict[str, str] | None = None

    def public_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "message": self.message,
            "remoteAccountId": self.remote_account_id,
            "details": self.details or {},
        }


class ConnectorAdapter(Protocol):
    manifest: ConnectorManifest

    async def test_connection(
        self,
        config: dict[str, Any],
        secrets: dict[str, str],
    ) -> ConnectorTestResult: ...
