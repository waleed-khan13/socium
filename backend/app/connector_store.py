from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from sqlalchemy import select

from app.connectors.registry import connector_catalog, get_manifest, validate_account_fields
from app.crypto import decrypt_secret, encrypt_secret
from app.database import read_session, write_session
from app.errors import AppError
from app.models import ConnectorAccount
from app.schemas import ConnectorAccountUpsert
from app.store import append_audit, utc_now


def _decrypt_secrets(value: str) -> dict[str, str]:
    try:
        payload = json.loads(decrypt_secret(value))
    except (RuntimeError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise RuntimeError("Saved connector secrets could not be decrypted.") from error
    if not isinstance(payload, dict) or not all(
        isinstance(key, str) and isinstance(item, str) for key, item in payload.items()
    ):
        raise RuntimeError("Saved connector secrets have an invalid shape.")
    return payload


def _encrypt_secrets(secrets: dict[str, str]) -> str:
    return encrypt_secret(json.dumps(secrets, separators=(",", ":"), sort_keys=True))


def _public_account(
    account: ConnectorAccount,
    listener_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manifest = get_manifest(account.adapter_id)
    try:
        saved_secret_keys = set(_decrypt_secrets(account.encrypted_secrets))
        vault_error = None
    except RuntimeError as error:
        saved_secret_keys = set()
        vault_error = str(error)
    missing_scopes = sorted(set(manifest.required_scopes) - set(account.scopes or []))
    scope_error = (
        f"Reconnect {manifest.name} to grant the new required scope: {', '.join(missing_scopes)}."
        if missing_scopes
        else None
    )
    return {
        "id": account.id,
        "adapterId": account.adapter_id,
        "adapterName": manifest.name,
        "name": account.name,
        "config": dict(account.config or {}),
        "secretStatus": {field.key: field.key in saved_secret_keys for field in manifest.secret_fields},
        "scopes": list(account.scopes or []),
        "capabilities": list(manifest.capabilities),
        "enabled": account.enabled,
        "status": "error" if vault_error or scope_error else account.status,
        "remoteAccountId": account.remote_account_id,
        "lastVerifiedAt": account.last_verified_at,
        "lastError": vault_error or scope_error or account.last_error,
        "listener": (
            {"active": False, "status": "stopped", "lastError": scope_error}
            if scope_error
            else listener_status or {"active": False, "status": "stopped", "lastError": None}
        ),
        "createdAt": account.created_at,
        "updatedAt": account.updated_at,
    }


def public_connector_state(
    listener_statuses: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    listener_statuses = listener_statuses or {}
    with read_session() as session:
        accounts = list(
            session.scalars(select(ConnectorAccount).order_by(ConnectorAccount.created_at.desc())).all()
        )
        return {
            "catalog": connector_catalog(),
            "accounts": [
                _public_account(
                    account,
                    listener_statuses.get(account.id)
                    if account.enabled and account.status == "verified"
                    else None,
                )
                for account in accounts
            ],
        }


def connector_runtime(account_id: str) -> dict[str, Any]:
    with read_session() as session:
        account = session.get(ConnectorAccount, account_id)
        if account is None:
            raise AppError("Connector account not found.", 404)
        return {
            "id": account.id,
            "adapter_id": account.adapter_id,
            "name": account.name,
            "config": dict(account.config or {}),
            "secrets": _decrypt_secrets(account.encrypted_secrets),
            "scopes": list(account.scopes or []),
            "enabled": account.enabled,
            "status": account.status,
            "updated_at": account.updated_at,
        }


def connector_runtimes(adapter_id: str, *, verified_only: bool = False) -> list[dict[str, Any]]:
    get_manifest(adapter_id)
    with read_session() as session:
        statement = select(ConnectorAccount).where(
            ConnectorAccount.adapter_id == adapter_id,
            ConnectorAccount.enabled.is_(True),
        )
        if verified_only:
            statement = statement.where(ConnectorAccount.status == "verified")
        accounts = list(session.scalars(statement.order_by(ConnectorAccount.created_at.asc())).all())
        runtimes: list[dict[str, Any]] = []
        for account in accounts:
            manifest = get_manifest(account.adapter_id)
            if set(manifest.required_scopes) - set(account.scopes or []):
                continue
            try:
                secrets = _decrypt_secrets(account.encrypted_secrets)
            except RuntimeError:
                continue
            runtimes.append(
                {
                    "id": account.id,
                    "adapter_id": account.adapter_id,
                    "name": account.name,
                    "config": dict(account.config or {}),
                    "secrets": secrets,
                    "scopes": list(account.scopes or []),
                    "enabled": account.enabled,
                    "status": account.status,
                    "updated_at": account.updated_at,
                }
            )
        return runtimes


def primary_connector_runtime(adapter_id: str, *, verified_only: bool = False) -> dict[str, Any]:
    runtimes = connector_runtimes(adapter_id, verified_only=verified_only)
    if not runtimes:
        if verified_only:
            raise AppError(f"Configure a verified {get_manifest(adapter_id).name} connector first.")
        raise AppError(f"Configure an enabled {get_manifest(adapter_id).name} connector first.")
    return runtimes[0]


def create_connector(payload: ConnectorAccountUpsert) -> dict[str, Any]:
    validate_account_fields(payload.adapter_id, payload.config, payload.secrets, payload.scopes)
    now = utc_now()
    with write_session() as session:
        duplicate = session.scalar(
            select(ConnectorAccount).where(
                ConnectorAccount.adapter_id == payload.adapter_id,
                ConnectorAccount.name == payload.name,
            )
        )
        if duplicate is not None:
            raise AppError("A connector account with this adapter and name already exists.")
        account = ConnectorAccount(
            id=str(uuid4()),
            adapter_id=payload.adapter_id,
            name=payload.name,
            config={
                key: value.strip() if isinstance(value, str) else value
                for key, value in payload.config.items()
            },
            encrypted_secrets=_encrypt_secrets(payload.secrets),
            scopes=payload.scopes,
            enabled=payload.enabled,
            status="saved",
            remote_account_id=None,
            last_verified_at=None,
            last_error=None,
            created_at=now,
            updated_at=now,
        )
        session.add(account)
        append_audit(
            session,
            action="connector.created",
            entity_type="connector",
            entity_id=account.id,
            summary=f"{get_manifest(account.adapter_id).name} connector account saved locally.",
        )
        session.flush()
        return _public_account(account)


def upsert_oauth_connector(payload: ConnectorAccountUpsert) -> dict[str, Any]:
    """Create or replace the first account for an OAuth-managed adapter."""
    with read_session() as session:
        existing_id = session.scalar(
            select(ConnectorAccount.id)
            .where(ConnectorAccount.adapter_id == payload.adapter_id)
            .order_by(ConnectorAccount.created_at.asc())
            .limit(1)
        )
    if existing_id:
        return update_connector(str(existing_id), payload)
    return create_connector(payload)


def update_connector(account_id: str, payload: ConnectorAccountUpsert) -> dict[str, Any]:
    with write_session() as session:
        account = session.get(ConnectorAccount, account_id)
        if account is None:
            raise AppError("Connector account not found.", 404)
        if account.adapter_id != payload.adapter_id:
            raise AppError("Connector adapter cannot be changed. Create a new account instead.")
        duplicate = session.scalar(
            select(ConnectorAccount).where(
                ConnectorAccount.adapter_id == payload.adapter_id,
                ConnectorAccount.name == payload.name,
                ConnectorAccount.id != account.id,
            )
        )
        if duplicate is not None:
            raise AppError("A connector account with this adapter and name already exists.")
        current_secrets = _decrypt_secrets(account.encrypted_secrets)
        validate_account_fields(
            payload.adapter_id,
            payload.config,
            payload.secrets,
            payload.scopes,
            set(current_secrets),
        )
        current_secrets.update(payload.secrets)
        account.name = payload.name
        account.config = {
            key: value.strip() if isinstance(value, str) else value for key, value in payload.config.items()
        }
        account.encrypted_secrets = _encrypt_secrets(current_secrets)
        account.scopes = payload.scopes
        account.enabled = payload.enabled
        account.status = "saved"
        account.remote_account_id = None
        account.last_verified_at = None
        account.last_error = None
        account.updated_at = utc_now()
        append_audit(
            session,
            action="connector.updated",
            entity_type="connector",
            entity_id=account.id,
            summary=f"{get_manifest(account.adapter_id).name} connector account updated locally.",
        )
        return _public_account(account)


def record_connector_test(account_id: str, *, ok: bool, remote_account_id: str | None, message: str) -> None:
    with write_session() as session:
        account = session.get(ConnectorAccount, account_id)
        if account is None:
            raise AppError("Connector account not found.", 404)
        account.status = "verified" if ok else "error"
        account.remote_account_id = remote_account_id if ok else account.remote_account_id
        account.last_verified_at = utc_now() if ok else account.last_verified_at
        account.last_error = None if ok else message[:2_000]
        account.updated_at = utc_now()
        append_audit(
            session,
            action="connector.verified" if ok else "connector.test_failed",
            entity_type="connector",
            entity_id=account.id,
            summary=message[:2_000],
        )


def delete_connector(account_id: str) -> None:
    with write_session() as session:
        account = session.get(ConnectorAccount, account_id)
        if account is None:
            raise AppError("Connector account not found.", 404)
        name = get_manifest(account.adapter_id).name
        session.delete(account)
        append_audit(
            session,
            action="connector.deleted",
            entity_type="connector",
            entity_id=account_id,
            summary=f"{name} connector account and its encrypted secrets were removed locally.",
        )
