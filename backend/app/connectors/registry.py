from __future__ import annotations

from typing import Any

from app.connectors.base import ConnectorAdapter, ConnectorManifest
from app.connectors.google_places import GooglePlacesAdapter
from app.connectors.instagram import InstagramAdapter
from app.connectors.linkedin import LinkedInMemberAdapter, LinkedInOrganizationAdapter
from app.connectors.meta import MetaPagesAdapter
from app.connectors.slack import SlackAdapter
from app.connectors.wordpress import WordPressAdapter
from app.errors import AppError

_slack = SlackAdapter()
_wordpress = WordPressAdapter()
_google_places = GooglePlacesAdapter()
_meta = MetaPagesAdapter()
_instagram = InstagramAdapter()
_linkedin = LinkedInMemberAdapter()
_linkedin_organization = LinkedInOrganizationAdapter()
_adapters: dict[str, ConnectorAdapter] = {
    "slack": _slack,
    "wordpress": _wordpress,
    "google-places": _google_places,
    "meta": _meta,
    "instagram": _instagram,
    "linkedin": _linkedin,
    "linkedin-organization": _linkedin_organization,
}

_catalog: tuple[ConnectorManifest, ...] = (
    ConnectorManifest(
        adapter_id="telegram",
        name="Telegram",
        description="Built-in long-polling approvals and Telegram publishing.",
        availability="built-in",
        capabilities=("approval", "notification", "publish"),
    ),
    _slack.manifest,
    _wordpress.manifest,
    _google_places.manifest,
    _meta.manifest,
    _instagram.manifest,
    _linkedin.manifest,
    _linkedin_organization.manifest,
)


def connector_catalog() -> list[dict[str, Any]]:
    return [manifest.public_dict() for manifest in _catalog]


def get_manifest(adapter_id: str) -> ConnectorManifest:
    manifest = next((item for item in _catalog if item.adapter_id == adapter_id), None)
    if manifest is None:
        raise AppError("Unknown connector adapter.", 404)
    return manifest


def get_adapter(adapter_id: str) -> ConnectorAdapter:
    manifest = get_manifest(adapter_id)
    adapter = _adapters.get(adapter_id)
    if adapter is None:
        raise AppError(f"{manifest.name} is listed honestly but is not installed yet.")
    return adapter


def validate_account_fields(
    adapter_id: str,
    config: dict[str, Any],
    secrets: dict[str, str],
    scopes: list[str],
    existing_secret_keys: set[str] | None = None,
) -> ConnectorManifest:
    manifest = get_adapter(adapter_id).manifest
    config_fields = {field.key: field for field in manifest.config_fields}
    secret_fields = {field.key: field for field in manifest.secret_fields}
    unknown_config = set(config) - set(config_fields)
    unknown_secrets = set(secrets) - set(secret_fields)
    if unknown_config:
        raise AppError(f"Unsupported connector config field: {min(unknown_config)}.")
    if unknown_secrets:
        raise AppError(f"Unsupported connector secret field: {min(unknown_secrets)}.")

    for key, field in config_fields.items():
        value = config.get(key)
        if value is not None and not isinstance(value, str):
            raise AppError(f"{field.label} must be text.")
        if isinstance(value, str) and len(value.strip()) > 2_000:
            raise AppError(f"{field.label} is too long.")
        if field.required and not str(value or "").strip():
            raise AppError(f"{field.label} is required.")

    available_secret_keys = set(secrets) | (existing_secret_keys or set())
    for key, field in secret_fields.items():
        if field.required and key not in available_secret_keys:
            raise AppError(f"{field.label} is required.")

    allowed_scopes = set(manifest.allowed_scopes)
    requested_scopes = set(scopes)
    unsupported_scopes = requested_scopes - allowed_scopes
    if unsupported_scopes:
        raise AppError(f"Unsupported connector scope: {min(unsupported_scopes)}.")
    missing_scopes = set(manifest.required_scopes) - requested_scopes
    if missing_scopes:
        raise AppError(f"Required connector scope missing: {min(missing_scopes)}.")
    return manifest
