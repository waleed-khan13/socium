from __future__ import annotations

import json
import re
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.orm import Session

from app import __version__
from app.config import get_settings
from app.crypto import decrypt_secret, encrypt_secret, serialize_legacy_secret
from app.database import read_session, run_migrations, write_session
from app.errors import AppError
from app.models import (
    AppMetadata,
    ApprovalAction,
    AuditEvent,
    AutomationRule,
    IcpProfile,
    ImageProviderSettings,
    LocalJob,
    MediaAsset,
    Post,
    ProviderSettings,
    TelegramSettings,
    Workspace,
)
from app.schemas import (
    AutomationRuleUpsert,
    BrandProfileUpdate,
    EditPostRequest,
    ImageProviderUpdate,
    JobRecoveryRequest,
    OnboardingUpdate,
    ProviderUpdate,
    SchedulePostRequest,
    TelegramUpdate,
    WorkspaceUpdate,
)

PUBLISHER_NAMES = {
    "telegram": "Telegram",
    "blog": "WordPress",
    "facebook": "Meta Pages",
    "instagram": "Instagram",
    "linkedin": "LinkedIn",
    "linkedin-company": "LinkedIn Company Page",
}


def publisher_name(channel: str) -> str:
    return PUBLISHER_NAMES.get(channel, channel.title())


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


_MEDIA_ID_IN_URL = re.compile(r"/api/media/([0-9a-fA-F-]{36})/")

PRIMARY_IMAGE_MODELS = {
    "gemini": ("gemini-images", "gemini-3.1-flash-image"),
    "openai": ("openai-images", "gpt-image-2"),
}


def primary_ai_capabilities(kind: str) -> dict[str, Any]:
    image = PRIMARY_IMAGE_MODELS.get(kind)
    return {
        "text": True,
        "image": image is not None,
        "imageModel": image[1] if image else None,
    }


def _utc_iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _text(value: object, maximum: int, default: str = "") -> str:
    if not isinstance(value, str):
        return default
    return value.strip()[:maximum]


def _legacy_secret(value: object) -> str | None:
    return serialize_legacy_secret(value)


def initialize_storage() -> None:
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    run_migrations()
    with write_session() as session:
        if session.get(Workspace, 1) is not None:
            _ensure_singletons(session)
        elif settings.legacy_json_path.exists():
            _import_legacy_json(session, settings.legacy_json_path)
        else:
            _seed_defaults(session)
        _recover_interrupted_approval_actions(session)
        _mark_overdue_jobs_for_recovery(
            session,
            "Socium was not running at the scheduled time. Choose Run now, Reschedule, or Skip.",
        )
    ensure_automation_jobs()


def _recover_interrupted_approval_actions(session: Session) -> None:
    interrupted = session.scalars(
        select(ApprovalAction).where(ApprovalAction.status.in_(("created", "processing")))
    ).all()
    if not interrupted:
        return
    now = utc_now()
    for action in interrupted:
        action.status = "failed"
        action.consumed_at = action.consumed_at or now
        action.last_error = "Socium restarted before this approval action completed. Send it again."


def _ensure_singletons(session: Session) -> None:
    if session.get(ProviderSettings, 1) is None:
        session.add(
            ProviderSettings(
                id=1,
                kind="ollama",
                base_url="http://127.0.0.1:11434",
                model="",
                api_key=None,
                updated_at=None,
            )
        )
    if session.get(ImageProviderSettings, 1) is None:
        session.add(
            ImageProviderSettings(
                id=1,
                kind="automatic1111",
                base_url="http://127.0.0.1:7860",
                model="",
                api_key=None,
                workflow_json=None,
                updated_at=None,
            )
        )
    if session.get(TelegramSettings, 1) is None:
        session.add(
            TelegramSettings(
                id=1,
                chat_id="",
                bot_token=None,
                polling_enabled=False,
                last_update_id=0,
                updated_at=None,
            )
        )
    if session.get(IcpProfile, 1) is None:
        session.add(
            IcpProfile(
                id=1,
                name="Primary ICP",
                target_keywords=[],
                excluded_keywords=[],
                target_locations=[],
                require_website=False,
                require_contact=False,
                version=0,
                updated_at=None,
            )
        )


def _seed_defaults(session: Session) -> None:
    session.add(
        Workspace(id=1, name="My workspace", business_name="", description="", timezone="Asia/Karachi")
    )
    _ensure_singletons(session)
    session.add(AppMetadata(key="storage_initialized_at", value=utc_now()))


def _import_legacy_json(session: Session, path: Path) -> None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("The existing socium.json store could not be imported.") from error
    if not isinstance(payload, dict):
        raise TypeError("The existing socium.json store has an invalid shape.")

    workspace = payload.get("workspace") if isinstance(payload.get("workspace"), dict) else {}
    provider = payload.get("provider") if isinstance(payload.get("provider"), dict) else {}
    telegram = payload.get("telegram") if isinstance(payload.get("telegram"), dict) else {}
    session.add(
        Workspace(
            id=1,
            name=_text(workspace.get("name"), 80, "My workspace") or "My workspace",
            business_name=_text(workspace.get("businessName"), 120),
            description=_text(workspace.get("description"), 2_000),
            timezone=_text(workspace.get("timezone"), 80, "Asia/Karachi") or "Asia/Karachi",
        )
    )
    session.add(
        ProviderSettings(
            id=1,
            kind=_text(provider.get("kind"), 40, "ollama") or "ollama",
            base_url=_text(provider.get("baseUrl"), 2_048, "http://127.0.0.1:11434")
            or "http://127.0.0.1:11434",
            model=_text(provider.get("model"), 180),
            api_key=_legacy_secret(provider.get("apiKey")),
            updated_at=_text(provider.get("updatedAt"), 40) or None,
        )
    )
    session.add(
        TelegramSettings(
            id=1,
            chat_id=_text(telegram.get("chatId"), 160),
            bot_token=_legacy_secret(telegram.get("botToken")),
            polling_enabled=False,
            last_update_id=max(int(telegram.get("lastUpdateId") or 0), 0),
            updated_at=_text(telegram.get("updatedAt"), 40) or None,
        )
    )

    allowed_channels = {
        "linkedin",
        "linkedin-company",
        "instagram",
        "facebook",
        "x",
        "telegram",
        "blog",
    }
    allowed_statuses = {
        "pending",
        "approved",
        "skipped",
        "rejected",
        "publishing",
        "published",
        "failed",
    }
    for raw_post in payload.get("posts", []):
        if not isinstance(raw_post, dict):
            continue
        post_id = _text(raw_post.get("id"), 36) or str(uuid4())
        created_at = _text(raw_post.get("createdAt"), 40) or utc_now()
        channel = _text(raw_post.get("channel"), 40, "linkedin")
        status = _text(raw_post.get("status"), 40, "pending")
        hashtags = raw_post.get("hashtags") if isinstance(raw_post.get("hashtags"), list) else []
        session.add(
            Post(
                id=post_id,
                revision=max(int(raw_post.get("revision") or 1), 1),
                topic=_text(raw_post.get("topic"), 1_000),
                channel=channel if channel in allowed_channels else "linkedin",
                tone=_text(raw_post.get("tone"), 160, "Clear and confident"),
                objective=_text(raw_post.get("objective"), 500, "Build useful awareness"),
                title=_text(raw_post.get("title"), 160, "Imported draft"),
                body=_text(raw_post.get("body"), 12_000),
                hashtags=[_text(tag, 80) for tag in hashtags if _text(tag, 80)][:20],
                media_url=_text(raw_post.get("mediaUrl"), 2_048) or None,
                rationale=_text(raw_post.get("rationale"), 500),
                status=status if status in allowed_statuses else "pending",
                provider_kind=_text(raw_post.get("providerKind"), 40, "ollama"),
                model=_text(raw_post.get("model"), 180),
                created_at=created_at,
                updated_at=_text(raw_post.get("updatedAt"), 40) or created_at,
                approved_at=_text(raw_post.get("approvedAt"), 40) or None,
                published_at=_text(raw_post.get("publishedAt"), 40) or None,
                remote_id=_text(raw_post.get("remoteId"), 255) or None,
                remote_url=_text(raw_post.get("remoteUrl"), 2_048) or None,
                last_error=_text(raw_post.get("lastError"), 2_000) or None,
            )
        )

    for raw_event in payload.get("audit", [])[:200]:
        if not isinstance(raw_event, dict):
            continue
        session.add(
            AuditEvent(
                id=_text(raw_event.get("id"), 36) or str(uuid4()),
                action=_text(raw_event.get("action"), 120, "legacy.imported"),
                entity_type=_text(raw_event.get("entityType"), 40, "settings"),
                entity_id=_text(raw_event.get("entityId"), 255, "legacy"),
                summary=_text(raw_event.get("summary"), 2_000, "Imported from the v0.2 local store."),
                created_at=_text(raw_event.get("createdAt"), 40) or utc_now(),
            )
        )
    session.add(AppMetadata(key="legacy_json_imported_at", value=utc_now()))
    _append_audit(
        session,
        action="storage.sqlite_imported",
        entity_type="settings",
        entity_id="storage",
        summary="The v0.2 JSON store was imported into the local SQLite database.",
    )


def _append_audit(
    session: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: str,
    summary: str,
) -> None:
    session.add(
        AuditEvent(
            id=str(uuid4()),
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            summary=summary,
            created_at=utc_now(),
        )
    )
    session.flush()
    old_ids = list(
        session.scalars(select(AuditEvent.id).order_by(AuditEvent.created_at.desc()).offset(200)).all()
    )
    if old_ids:
        session.execute(delete(AuditEvent).where(AuditEvent.id.in_(old_ids)))


def append_audit(
    session: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: str,
    summary: str,
) -> None:
    _append_audit(
        session,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        summary=summary,
    )


def _post_dict(post: Post) -> dict[str, Any]:
    return {
        "id": post.id,
        "revision": post.revision,
        "topic": post.topic,
        "channel": post.channel,
        "tone": post.tone,
        "objective": post.objective,
        "title": post.title,
        "body": post.body,
        "hashtags": list(post.hashtags or []),
        "callToAction": post.call_to_action,
        "imagePrompt": post.image_prompt,
        "imageNegativePrompt": post.image_negative_prompt,
        "imageAltText": post.image_alt_text,
        "brandProfileVersion": post.brand_profile_version,
        "mediaAssetId": post.media_asset_id,
        "mediaPreviewUrl": f"/api/media/{post.media_asset_id}/preview" if post.media_asset_id else None,
        "mediaUrl": post.media_url,
        "rationale": post.rationale,
        "status": post.status,
        "providerKind": post.provider_kind,
        "model": post.model,
        "createdAt": post.created_at,
        "updatedAt": post.updated_at,
        "approvedAt": post.approved_at,
        "publishedAt": post.published_at,
        "remoteId": post.remote_id,
        "remoteUrl": post.remote_url,
        "lastError": post.last_error,
        "automationId": post.automation_id,
        "automationPublishAt": post.automation_publish_at,
    }


def _job_dict(job: LocalJob) -> dict[str, Any]:
    return {
        "id": job.id,
        "kind": job.kind,
        "status": job.status,
        "payload": dict(job.payload or {}),
        "runAt": job.run_at,
        "attempts": job.attempts,
        "maxAttempts": job.max_attempts,
        "lockedAt": job.locked_at,
        "leaseExpiresAt": job.lease_expires_at,
        "recoveryRequiredAt": job.recovery_required_at,
        "recoveryReason": job.recovery_reason,
        "completedAt": job.completed_at,
        "lastError": job.last_error,
        "progressPercent": job.progress_percent,
        "progressMessage": job.progress_message,
        "cancelRequested": job.cancel_requested,
        "remoteRef": job.remote_ref,
        "resultRef": job.result_ref,
        "createdAt": job.created_at,
        "updatedAt": job.updated_at,
    }


def _automation_dict(rule: AutomationRule) -> dict[str, Any]:
    return {
        "id": rule.id,
        "name": rule.name,
        "enabled": rule.enabled,
        "channel": rule.channel,
        "topic": rule.topic,
        "tone": rule.tone,
        "objective": rule.objective,
        "timezone": rule.timezone,
        "daysOfWeek": list(rule.days_of_week or []),
        "postsPerWeek": len(rule.days_of_week or []),
        "publishTime": rule.publish_time,
        "approvalChannels": list(rule.approval_channels or []),
        "generateAheadMinutes": rule.generate_ahead_minutes,
        "publishAfterApproval": rule.publish_after_approval,
        "nextRunAt": rule.next_run_at,
        "nextPublishAt": rule.next_publish_at,
        "lastRunAt": rule.last_run_at,
        "lastError": rule.last_error,
        "createdAt": rule.created_at,
        "updatedAt": rule.updated_at,
    }


def _brand_missing(workspace: Workspace) -> list[str]:
    required = {
        "businessName": workspace.business_name,
        "description": workspace.description,
        "productsServices": workspace.products_services,
        "targetAudience": workspace.target_audience,
        "goals": workspace.goals,
        "callToAction": workspace.call_to_action,
        "language": workspace.language,
        "tone": workspace.tone,
        "contentPillars": workspace.content_pillars,
    }
    return [field for field, value in required.items() if not value]


def _brand_asset(asset: MediaAsset | None) -> dict[str, Any] | None:
    if asset is None:
        return None
    return {
        "id": asset.id,
        "originalName": asset.original_name,
        "previewUrl": f"/api/media/{asset.id}/preview",
        "altText": asset.alt_text,
    }


def _workspace_dict(session: Session, workspace: Workspace) -> dict[str, Any]:
    missing = _brand_missing(workspace)
    logo = session.get(MediaAsset, workspace.logo_media_id) if workspace.logo_media_id else None
    references = [
        asset
        for asset_id in (workspace.reference_media_ids or [])
        if (asset := session.get(MediaAsset, asset_id)) is not None
    ]
    return {
        "name": workspace.name,
        "businessName": workspace.business_name,
        "description": workspace.description,
        "timezone": workspace.timezone,
        "website": workspace.website,
        "industry": workspace.industry,
        "productsServices": workspace.products_services,
        "targetAudience": workspace.target_audience,
        "location": workspace.location,
        "goals": list(workspace.goals or []),
        "callToAction": workspace.call_to_action,
        "language": workspace.language,
        "tone": workspace.tone,
        "contentPillars": list(workspace.content_pillars or []),
        "restrictedClaims": list(workspace.restricted_claims or []),
        "brandedHashtags": list(workspace.branded_hashtags or []),
        "logoMediaId": workspace.logo_media_id if logo else None,
        "logo": _brand_asset(logo),
        "referenceMediaIds": [asset.id for asset in references],
        "referenceMedia": [_brand_asset(asset) for asset in references],
        "primaryColor": workspace.primary_color,
        "secondaryColor": workspace.secondary_color,
        "accentColor": workspace.accent_color,
        "headingFont": workspace.heading_font,
        "bodyFont": workspace.body_font,
        "visualStyle": workspace.visual_style,
        "profileVersion": workspace.profile_version,
        "confirmedAt": workspace.confirmed_at,
        "updatedAt": workspace.updated_at,
        "profileComplete": bool(workspace.confirmed_at and not missing),
        "missingFields": missing,
    }


ONBOARDING_KEYS = (
    "onboarding_started_at",
    "onboarding_current_step",
    "onboarding_storage_snapshot",
    "onboarding_storage_confirmed_at",
    "onboarding_dismissed_at",
    "onboarding_completed_at",
)


def _metadata_value(session: Session, key: str) -> str | None:
    metadata = session.get(AppMetadata, key)
    return metadata.value if metadata is not None else None


def _set_metadata(session: Session, key: str, value: str) -> None:
    metadata = session.get(AppMetadata, key)
    if metadata is None:
        session.add(AppMetadata(key=key, value=value))
    else:
        metadata.value = value


def _provider_fingerprint(provider: ProviderSettings) -> str:
    return json.dumps(
        {
            "kind": provider.kind,
            "baseUrl": provider.base_url,
            "model": provider.model,
            "updatedAt": provider.updated_at,
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def _storage_snapshot(storage: dict[str, Any]) -> str:
    locations = storage.get("locations") or {}
    return json.dumps(
        {
            "data": (locations.get("data") or {}).get("path", ""),
            "models": (locations.get("models") or {}).get("path", ""),
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def _onboarding_dict(
    session: Session,
    workspace: Workspace,
    provider: ProviderSettings,
    storage: dict[str, Any],
) -> dict[str, Any]:
    started_at = _metadata_value(session, "onboarding_started_at")
    dismissed_at = _metadata_value(session, "onboarding_dismissed_at")
    completed_at = _metadata_value(session, "onboarding_completed_at")
    current_step = _metadata_value(session, "onboarding_current_step") or "welcome"
    if current_step not in {"welcome", "storage", "ai", "brand", "finish"}:
        current_step = "welcome"
    storage_confirmed = bool(
        _metadata_value(session, "onboarding_storage_confirmed_at")
        and _metadata_value(session, "onboarding_storage_snapshot") == _storage_snapshot(storage)
    )
    provider_configured = bool(provider.base_url and provider.model)
    provider_verified = bool(
        provider_configured
        and _metadata_value(session, "provider_verified_snapshot") == _provider_fingerprint(provider)
    )
    profile_complete = bool(workspace.confirmed_at and not _brand_missing(workspace))
    ready = storage_confirmed and provider_verified and profile_complete
    status = (
        "completed"
        if completed_at
        else "dismissed"
        if dismissed_at
        else "in-progress"
        if started_at
        else "not-started"
    )
    return {
        "version": 1,
        "status": status,
        "showWizard": status in {"not-started", "in-progress"},
        "currentStep": "finish" if completed_at else current_step,
        "startedAt": started_at,
        "dismissedAt": dismissed_at,
        "completedAt": completed_at,
        "storageConfirmed": storage_confirmed,
        "storageReady": bool(
            (storage.get("volumes") or {}).get("data", {}).get("available")
            and (storage.get("volumes") or {}).get("models", {}).get("available")
        ),
        "aiConfigured": provider_configured,
        "aiVerified": provider_verified,
        "brandConfirmed": profile_complete,
        "ready": ready,
        "completedSteps": sum((storage_confirmed, provider_verified, profile_complete)),
        "totalSteps": 3,
    }


def onboarding_state(storage: dict[str, Any]) -> dict[str, Any]:
    with read_session() as session:
        workspace = session.get(Workspace, 1)
        provider = session.get(ProviderSettings, 1)
        if workspace is None or provider is None:
            raise RuntimeError("Local storage has not been initialized.")
        return _onboarding_dict(session, workspace, provider, storage)


def update_onboarding(payload: OnboardingUpdate, storage: dict[str, Any]) -> None:
    with write_session() as session:
        workspace = session.get(Workspace, 1)
        provider = session.get(ProviderSettings, 1)
        if workspace is None or provider is None:
            raise RuntimeError("Local storage has not been initialized.")
        now = utc_now()
        if payload.action == "reset":
            for key in ONBOARDING_KEYS:
                metadata = session.get(AppMetadata, key)
                if metadata is not None:
                    session.delete(metadata)
            return
        if payload.action == "start":
            if _metadata_value(session, "onboarding_started_at") is None:
                _set_metadata(session, "onboarding_started_at", now)
            dismissed = session.get(AppMetadata, "onboarding_dismissed_at")
            if dismissed is not None:
                session.delete(dismissed)
            return
        if payload.action == "set-step":
            _set_metadata(session, "onboarding_current_step", payload.step or "welcome")
            return
        if payload.action == "confirm-storage":
            volumes = storage.get("volumes") or {}
            if not (volumes.get("data") or {}).get("available") or not (volumes.get("models") or {}).get(
                "available"
            ):
                raise AppError("The selected data and model drives must both be available.")
            if storage.get("warnings") and not payload.acknowledge_warnings:
                raise AppError("Review and acknowledge the storage warnings before continuing.")
            _set_metadata(session, "onboarding_storage_snapshot", _storage_snapshot(storage))
            _set_metadata(session, "onboarding_storage_confirmed_at", now)
            _set_metadata(session, "onboarding_current_step", "ai")
            _append_audit(
                session,
                action="onboarding.storage_confirmed",
                entity_type="settings",
                entity_id="onboarding",
                summary="Confirmed the active durable data and local model locations.",
            )
            return
        if payload.action == "dismiss":
            _set_metadata(session, "onboarding_dismissed_at", now)
            _append_audit(
                session,
                action="onboarding.dismissed",
                entity_type="settings",
                entity_id="onboarding",
                summary="First-run setup was dismissed and can be resumed later.",
            )
            return
        state = _onboarding_dict(session, workspace, provider, storage)
        if not state["ready"]:
            missing = []
            if not state["storageConfirmed"]:
                missing.append("storage confirmation")
            if not state["aiVerified"]:
                missing.append("a verified AI provider")
            if not state["brandConfirmed"]:
                missing.append("a confirmed brand profile")
            raise AppError(f"Finish {', '.join(missing)} before completing setup.")
        _set_metadata(session, "onboarding_completed_at", now)
        _set_metadata(session, "onboarding_current_step", "finish")
        dismissed = session.get(AppMetadata, "onboarding_dismissed_at")
        if dismissed is not None:
            session.delete(dismissed)
        _append_audit(
            session,
            action="onboarding.completed",
            entity_type="settings",
            entity_id="onboarding",
            summary="Completed local-first setup with verified storage, AI, and brand context.",
        )


def record_provider_verified() -> None:
    with write_session() as session:
        provider = session.get(ProviderSettings, 1)
        if provider is None or not provider.base_url or not provider.model:
            raise AppError("Choose a working provider model before verification.")
        _set_metadata(session, "provider_verified_snapshot", _provider_fingerprint(provider))
        _set_metadata(session, "provider_verified_at", utc_now())
        _append_audit(
            session,
            action="provider.verified",
            entity_type="provider",
            entity_id=provider.kind,
            summary=f"Verified the saved {provider.kind} provider and selected model.",
        )


def public_state(
    polling: dict[str, Any] | None = None,
    scheduler: dict[str, Any] | None = None,
) -> dict[str, Any]:
    polling = polling or {"active": False, "status": "stopped", "lastError": None}
    scheduler = scheduler or {"active": False, "status": "stopped", "lastError": None}
    with read_session() as session:
        workspace = session.get(Workspace, 1)
        provider = session.get(ProviderSettings, 1)
        image_provider = session.get(ImageProviderSettings, 1)
        telegram = session.get(TelegramSettings, 1)
        if workspace is None or provider is None or image_provider is None or telegram is None:
            raise RuntimeError("Local storage has not been initialized.")
        posts = list(session.scalars(select(Post).order_by(Post.created_at.desc())).all())
        automations = list(
            session.scalars(select(AutomationRule).order_by(AutomationRule.created_at.desc())).all()
        )
        audit = list(
            session.scalars(select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(200)).all()
        )
        jobs = list(
            session.scalars(
                select(LocalJob)
                .where(LocalJob.kind == "post.publish")
                .order_by(LocalJob.created_at.desc())
                .limit(100)
            ).all()
        )
        paused = session.get(AppMetadata, "scheduler_paused")
        recovery_pending = len(
            session.scalars(
                select(LocalJob.id).where(
                    LocalJob.kind == "post.publish",
                    LocalJob.status == "missed",
                    LocalJob.recovery_required_at.is_not(None),
                )
            ).all()
        )
        provider_verified = bool(
            provider.base_url
            and provider.model
            and _metadata_value(session, "provider_verified_snapshot") == _provider_fingerprint(provider)
        )
        provider_capabilities = primary_ai_capabilities(provider.kind)
        remote_edit_request: dict[str, Any] | None = None
        raw_edit_request = _metadata_value(session, "remote_edit_request")
        if raw_edit_request:
            try:
                parsed_edit_request = json.loads(raw_edit_request)
            except (TypeError, ValueError, json.JSONDecodeError):
                parsed_edit_request = None
            if isinstance(parsed_edit_request, dict):
                remote_edit_request = parsed_edit_request
        return {
            "workspace": _workspace_dict(session, workspace),
            "provider": {
                "kind": provider.kind,
                "baseUrl": provider.base_url,
                "model": provider.model,
                "hasApiKey": bool(provider.api_key),
                "configured": bool(provider.base_url and provider.model),
                "verified": provider_verified,
                "capabilities": provider_capabilities,
                "updatedAt": provider.updated_at,
            },
            "imageProvider": {
                "kind": PRIMARY_IMAGE_MODELS.get(provider.kind, (image_provider.kind, ""))[0],
                "baseUrl": provider.base_url,
                "model": provider_capabilities["imageModel"] or "",
                "hasApiKey": bool(provider.api_key),
                "hasWorkflow": False,
                "configured": bool(
                    provider_verified and provider_capabilities["image"] and provider.api_key
                ),
                "updatedAt": provider.updated_at,
            },
            "telegram": {
                "chatId": telegram.chat_id,
                "hasBotToken": bool(telegram.bot_token),
                "hasProxy": bool(telegram.proxy_url),
                "configured": bool(telegram.chat_id and telegram.bot_token),
                "pollingEnabled": telegram.polling_enabled,
                "pollingActive": bool(polling.get("active")),
                "pollingStatus": str(polling.get("status") or "stopped"),
                "lastError": polling.get("lastError"),
                "updatedAt": telegram.updated_at,
            },
            "posts": [_post_dict(post) for post in posts],
            "automations": [_automation_dict(rule) for rule in automations],
            "remoteEditRequest": remote_edit_request,
            "jobs": [_job_dict(job) for job in jobs],
            "scheduler": {
                "paused": paused is not None and paused.value == "true",
                "active": bool(scheduler.get("active")),
                "status": str(scheduler.get("status") or "stopped"),
                "lastError": scheduler.get("lastError"),
                "catchUpHours": int(scheduler.get("catchUpHours") or 24),
                "resourceMode": str(scheduler.get("resourceMode") or "idle"),
                "workerLimit": int(scheduler.get("workerLimit") or 1),
                "workersActive": int(scheduler.get("workersActive") or 0),
                "nextWakeAt": scheduler.get("nextWakeAt"),
                "idleSince": scheduler.get("idleSince"),
                "crashCount": int(scheduler.get("crashCount") or 0),
                "recoveryPending": recovery_pending,
            },
            "audit": [
                {
                    "id": event.id,
                    "action": event.action,
                    "entityType": event.entity_type,
                    "entityId": event.entity_id,
                    "summary": event.summary,
                    "createdAt": event.created_at,
                }
                for event in audit
            ],
            "runtime": {
                "version": __version__,
                "mode": "local_only",
                "persistent": True,
                "database": "sqlite",
            },
        }


def update_workspace(payload: WorkspaceUpdate) -> None:
    with write_session() as session:
        workspace = session.get(Workspace, 1)
        if workspace is None:
            raise RuntimeError("Workspace settings are missing.")
        workspace.name = payload.name
        workspace.business_name = payload.business_name
        workspace.description = payload.description
        workspace.timezone = payload.timezone or "Asia/Karachi"
        workspace.confirmed_at = None
        workspace.updated_at = utc_now()
        _append_audit(
            session,
            action="workspace.updated",
            entity_type="settings",
            entity_id="workspace",
            summary="Business profile updated.",
        )


def update_brand_profile(payload: BrandProfileUpdate) -> None:
    with write_session() as session:
        workspace = session.get(Workspace, 1)
        if workspace is None:
            raise RuntimeError("Workspace settings are missing.")
        media_ids = [
            media_id for media_id in [payload.logo_media_id, *payload.reference_media_ids] if media_id
        ]
        missing_assets = [media_id for media_id in media_ids if session.get(MediaAsset, media_id) is None]
        if missing_assets:
            raise AppError("One or more selected brand images no longer exist in the media library.")
        now = utc_now()
        workspace.name = payload.name
        workspace.business_name = payload.business_name
        workspace.description = payload.description
        workspace.timezone = payload.timezone
        workspace.website = payload.website
        workspace.industry = payload.industry
        workspace.products_services = payload.products_services
        workspace.target_audience = payload.target_audience
        workspace.location = payload.location
        workspace.goals = payload.goals
        workspace.call_to_action = payload.call_to_action
        workspace.language = payload.language
        workspace.tone = payload.tone
        workspace.content_pillars = payload.content_pillars
        workspace.restricted_claims = payload.restricted_claims
        workspace.branded_hashtags = payload.branded_hashtags
        workspace.logo_media_id = payload.logo_media_id
        workspace.reference_media_ids = payload.reference_media_ids
        workspace.primary_color = payload.primary_color.lower()
        workspace.secondary_color = payload.secondary_color.lower()
        workspace.accent_color = payload.accent_color.lower()
        workspace.heading_font = payload.heading_font
        workspace.body_font = payload.body_font
        workspace.visual_style = payload.visual_style
        workspace.profile_version += 1
        workspace.confirmed_at = now
        workspace.updated_at = now
        _append_audit(
            session,
            action="brand_profile.confirmed",
            entity_type="settings",
            entity_id="brand-profile",
            summary=f"Confirmed brand profile revision {workspace.profile_version}.",
        )


def _previous_brand_data(session: Session) -> dict[str, Any]:
    workspace = session.get(Workspace, 1)
    if workspace is None:
        raise RuntimeError("Workspace settings are missing.")

    posts = list(
        session.scalars(
            select(Post).where(Post.brand_profile_version < workspace.profile_version)
        ).all()
    )
    post_ids = {post.id for post in posts}
    jobs = [
        job
        for job in session.scalars(select(LocalJob)).all()
        if str((job.payload or {}).get("post_id") or "") in post_ids
    ]
    job_ids = {job.id for job in jobs}
    approvals = (
        list(
            session.scalars(
                select(ApprovalAction).where(ApprovalAction.post_id.in_(post_ids))
            ).all()
        )
        if post_ids
        else []
    )

    referenced_media_ids = {
        str(asset_id)
        for asset_id in [workspace.logo_media_id, *(workspace.reference_media_ids or [])]
        if asset_id
    }
    current_posts = session.scalars(
        select(Post).where(Post.brand_profile_version >= workspace.profile_version)
    ).all()
    for post in current_posts:
        match = _MEDIA_ID_IN_URL.search(str(post.media_url or ""))
        if match:
            referenced_media_ids.add(match.group(1))
    unused_website_media = [
        asset
        for asset in session.scalars(
            select(MediaAsset).where(MediaAsset.source == "website-import")
        ).all()
        if asset.id not in referenced_media_ids
    ]
    media_ids = {asset.id for asset in unused_website_media}

    audit_entity_ids = post_ids | job_ids | media_ids
    audit_conditions = []
    if audit_entity_ids:
        audit_conditions.append(AuditEvent.entity_id.in_(audit_entity_ids))
    if workspace.confirmed_at:
        audit_conditions.append(
            and_(
                AuditEvent.action == "brand_profile.confirmed",
                AuditEvent.created_at < workspace.confirmed_at,
            )
        )
    audits = (
        list(session.scalars(select(AuditEvent).where(or_(*audit_conditions))).all())
        if audit_conditions
        else []
    )
    return {
        "currentBusinessName": workspace.business_name,
        "currentProfileVersion": workspace.profile_version,
        "posts": len(posts),
        "publishedPosts": sum(1 for post in posts if post.status == "published"),
        "approvalActions": len(approvals),
        "scheduledJobs": len(jobs),
        "auditEvents": len(audits),
        "mediaAssets": len(unused_website_media),
        "_postIds": sorted(post_ids),
        "_jobIds": sorted(job_ids),
        "_auditIds": sorted(event.id for event in audits),
        "_mediaIds": sorted(media_ids),
    }


def previous_brand_data_summary() -> dict[str, Any]:
    with read_session() as session:
        summary = _previous_brand_data(session)
        return {key: value for key, value in summary.items() if not key.startswith("_")}


def delete_previous_brand_data(current_business_name: str) -> dict[str, Any]:
    with write_session() as session:
        summary = _previous_brand_data(session)
        if current_business_name != summary["currentBusinessName"]:
            raise AppError("The active business changed. Review the cleanup details and try again.", 409)

        post_ids = summary["_postIds"]
        publishing = (
            session.scalar(
                select(Post.id).where(
                    Post.id.in_(post_ids),
                    Post.status == "publishing",
                )
            )
            if post_ids
            else None
        )
        if publishing:
            raise AppError("A previous-brand post is currently publishing. Wait for it to finish.", 409)

        if summary["_auditIds"]:
            session.execute(delete(AuditEvent).where(AuditEvent.id.in_(summary["_auditIds"])))
        if post_ids:
            session.execute(
                delete(ApprovalAction).where(ApprovalAction.post_id.in_(post_ids))
            )
        if summary["_jobIds"]:
            session.execute(delete(LocalJob).where(LocalJob.id.in_(summary["_jobIds"])))
        if post_ids:
            session.execute(delete(Post).where(Post.id.in_(post_ids)))

        if any(
            int(summary[key])
            for key in ("posts", "approvalActions", "scheduledJobs", "auditEvents", "mediaAssets")
        ):
            _append_audit(
                session,
                action="brand_history.deleted",
                entity_type="settings",
                entity_id="brand-profile",
                summary="Deleted previous brand content and local history.",
            )
        return summary


def update_provider(payload: ProviderUpdate) -> None:
    with write_session() as session:
        provider = session.get(ProviderSettings, 1)
        if provider is None:
            raise RuntimeError("Provider settings are missing.")
        same_endpoint = provider.kind == payload.kind and provider.base_url == payload.base_url
        provider.kind = payload.kind
        provider.base_url = payload.base_url.rstrip("/")
        provider.model = payload.model
        provider.api_key = (
            encrypt_secret(payload.api_key)
            if payload.api_key
            else provider.api_key
            if same_endpoint
            else None
        )
        provider.updated_at = utc_now()
        verified = session.get(AppMetadata, "provider_verified_snapshot")
        if verified is not None:
            session.delete(verified)
        verified_at = session.get(AppMetadata, "provider_verified_at")
        if verified_at is not None:
            session.delete(verified_at)
        _append_audit(
            session,
            action="provider.updated",
            entity_type="provider",
            entity_id=provider.kind,
            summary=f"{provider.kind} provider settings saved.",
        )


def update_image_provider(payload: ImageProviderUpdate) -> None:
    with write_session() as session:
        provider = session.get(ImageProviderSettings, 1)
        if provider is None:
            raise RuntimeError("Image provider settings are missing.")
        normalized_url = payload.base_url.rstrip("/")
        same_endpoint = provider.kind == payload.kind and provider.base_url == normalized_url
        workflow_json = (
            payload.workflow_json
            if payload.workflow_json
            else provider.workflow_json
            if same_endpoint
            else None
        )
        if payload.kind == "comfyui" and not workflow_json:
            raise AppError("Paste a ComfyUI workflow exported in API format before saving.")
        provider.kind = payload.kind
        provider.base_url = normalized_url
        provider.model = payload.model
        provider.api_key = (
            encrypt_secret(payload.api_key)
            if payload.api_key
            else provider.api_key
            if same_endpoint
            else None
        )
        provider.workflow_json = workflow_json if payload.kind == "comfyui" else None
        provider.updated_at = utc_now()
        _append_audit(
            session,
            action="image_provider.updated",
            entity_type="provider",
            entity_id=provider.kind,
            summary=f"{provider.kind} image provider settings saved.",
        )


def update_telegram(payload: TelegramUpdate) -> None:
    with write_session() as session:
        telegram = session.get(TelegramSettings, 1)
        if telegram is None:
            raise RuntimeError("Telegram settings are missing.")
        if payload.bot_token:
            telegram.bot_token = encrypt_secret(payload.bot_token)
            telegram.polling_enabled = False
            telegram.last_update_id = 0
        if payload.clear_proxy:
            telegram.proxy_url = None
        elif payload.proxy_url:
            telegram.proxy_url = encrypt_secret(payload.proxy_url)
        telegram.chat_id = payload.chat_id
        telegram.updated_at = utc_now()
        _append_audit(
            session,
            action="telegram.updated",
            entity_type="settings",
            entity_id="telegram",
            summary="Telegram connection settings saved.",
        )


def save_telegram_token(
    bot_token: str,
    *,
    proxy_url: str = "",
    clear_proxy: bool = False,
) -> None:
    with write_session() as session:
        telegram = session.get(TelegramSettings, 1)
        if telegram is None:
            raise RuntimeError("Telegram settings are missing.")
        telegram.bot_token = encrypt_secret(bot_token)
        if clear_proxy:
            telegram.proxy_url = None
        elif proxy_url:
            telegram.proxy_url = encrypt_secret(proxy_url)
        telegram.chat_id = ""
        telegram.polling_enabled = False
        telegram.last_update_id = 0
        telegram.updated_at = utc_now()
        _append_audit(
            session,
            action="telegram.bot_verified",
            entity_type="settings",
            entity_id="telegram",
            summary="Saved a verified Telegram bot token and started automatic chat discovery.",
        )


def update_telegram_proxy(proxy_url: str, *, clear: bool = False) -> None:
    with write_session() as session:
        telegram = session.get(TelegramSettings, 1)
        if telegram is None:
            raise RuntimeError("Telegram settings are missing.")
        telegram.proxy_url = None if clear else encrypt_secret(proxy_url)
        telegram.updated_at = utc_now()
        _append_audit(
            session,
            action="telegram.proxy_updated",
            entity_type="settings",
            entity_id="telegram",
            summary="Telegram-only network proxy settings updated locally.",
        )


def complete_telegram_connection(chat_id: str, update_id: int) -> None:
    with write_session() as session:
        telegram = session.get(TelegramSettings, 1)
        if telegram is None or not telegram.bot_token:
            raise AppError("Save a Telegram bot token before discovering its approval chat.")
        telegram.chat_id = chat_id
        telegram.last_update_id = max(update_id, 0)
        telegram.polling_enabled = True
        telegram.updated_at = utc_now()
        _append_audit(
            session,
            action="telegram.connected",
            entity_type="settings",
            entity_id="telegram",
            summary="Automatically discovered the Telegram approval chat and started local approvals.",
        )


def set_telegram_polling(enabled: bool) -> None:
    with write_session() as session:
        telegram = session.get(TelegramSettings, 1)
        if telegram is None or not telegram.bot_token or not telegram.chat_id:
            raise AppError("Save and test Telegram before starting local approvals.")
        telegram.polling_enabled = enabled
        telegram.updated_at = utc_now()
        _append_audit(
            session,
            action="telegram.polling_started" if enabled else "telegram.polling_stopped",
            entity_type="settings",
            entity_id="telegram",
            summary="Local Telegram approval polling started."
            if enabled
            else "Local Telegram approval polling stopped.",
        )


def provider_runtime() -> dict[str, str]:
    with read_session() as session:
        provider = session.get(ProviderSettings, 1)
        if provider is None:
            raise RuntimeError("Provider settings are missing.")
        return {
            "kind": provider.kind,
            "base_url": provider.base_url,
            "model": provider.model,
            "api_key": decrypt_secret(provider.api_key),
        }


def primary_image_runtime() -> dict[str, str]:
    with read_session() as session:
        provider = session.get(ProviderSettings, 1)
        if provider is None:
            raise RuntimeError("Provider settings are missing.")
        image = PRIMARY_IMAGE_MODELS.get(provider.kind)
        if image is None:
            raise AppError(
                "The connected AI provider does not expose image generation through the same connection."
            )
        if not provider.api_key:
            raise AppError("The connected AI provider requires its saved API key for image generation.")
        return {
            "kind": image[0],
            "base_url": provider.base_url,
            "model": image[1],
            "api_key": decrypt_secret(provider.api_key),
            "workflow_json": "",
            "updated_at": provider.updated_at or "",
        }


def image_provider_runtime() -> dict[str, str]:
    with read_session() as session:
        provider = session.get(ImageProviderSettings, 1)
        if provider is None:
            raise RuntimeError("Image provider settings are missing.")
        return {
            "kind": provider.kind,
            "base_url": provider.base_url,
            "model": provider.model,
            "api_key": decrypt_secret(provider.api_key),
            "workflow_json": provider.workflow_json or "",
            "updated_at": provider.updated_at or "",
        }


def telegram_runtime() -> dict[str, Any]:
    with read_session() as session:
        telegram = session.get(TelegramSettings, 1)
        if telegram is None:
            raise RuntimeError("Telegram settings are missing.")
        return {
            "chat_id": telegram.chat_id,
            "bot_token": decrypt_secret(telegram.bot_token),
            "proxy_url": decrypt_secret(telegram.proxy_url),
            "polling_enabled": telegram.polling_enabled,
            "last_update_id": telegram.last_update_id,
        }


def workspace_runtime() -> dict[str, Any]:
    with read_session() as session:
        workspace = session.get(Workspace, 1)
        if workspace is None:
            raise RuntimeError("Workspace settings are missing.")
        confirmed = bool(workspace.confirmed_at and not _brand_missing(workspace))
        runtime: dict[str, Any] = {
            "business_name": workspace.business_name,
            "business_description": workspace.description,
            "profile_confirmed": confirmed,
        }
        if confirmed:
            runtime.update(
                {
                    "website": workspace.website,
                    "industry": workspace.industry,
                    "products_services": workspace.products_services,
                    "target_audience": workspace.target_audience,
                    "location": workspace.location,
                    "goals": list(workspace.goals or []),
                    "call_to_action": workspace.call_to_action,
                    "language": workspace.language,
                    "tone": workspace.tone,
                    "content_pillars": list(workspace.content_pillars or []),
                    "restricted_claims": list(workspace.restricted_claims or []),
                    "branded_hashtags": list(workspace.branded_hashtags or []),
                    "brand_colors": [
                        workspace.primary_color,
                        workspace.secondary_color,
                        workspace.accent_color,
                    ],
                    "heading_font": workspace.heading_font,
                    "body_font": workspace.body_font,
                    "visual_style": workspace.visual_style,
                    "logo_media_id": workspace.logo_media_id,
                    "profile_version": workspace.profile_version,
                }
            )
        return runtime


def create_post(
    *,
    request: dict[str, Any],
    content: dict[str, Any],
    provider: dict[str, str],
    brand_profile_version: int = 0,
    automation_id: str | None = None,
    automation_publish_at: str | None = None,
) -> dict[str, Any]:
    now = utc_now()
    post = Post(
        id=str(uuid4()),
        revision=1,
        topic=request["topic"],
        channel=request["channel"],
        tone=request["tone"],
        objective=request["objective"],
        title=content["title"],
        body=content["body"],
        hashtags=content.get("hashtags", []),
        call_to_action=content.get("call_to_action", ""),
        image_prompt=content.get("image_prompt", ""),
        image_negative_prompt=content.get("image_negative_prompt", ""),
        image_alt_text=content.get("image_alt_text", ""),
        brand_profile_version=brand_profile_version,
        media_asset_id=request.get("media_asset_id") or None,
        media_url=request.get("media_url") or None,
        rationale=content.get("rationale", ""),
        status="pending",
        provider_kind=provider["kind"],
        model=provider["model"],
        created_at=now,
        updated_at=now,
        approved_at=None,
        published_at=None,
        remote_id=None,
        remote_url=None,
        last_error=None,
        automation_id=automation_id,
        automation_publish_at=automation_publish_at,
    )
    with write_session() as session:
        session.add(post)
        _append_audit(
            session,
            action="post.generated",
            entity_type="post",
            entity_id=post.id,
            summary=f"{post.channel} draft generated with {post.model}.",
        )
    return _post_dict(post)


def create_approval_action(
    post_id: str,
    revision: int,
    source: Literal["telegram", "slack"],
) -> dict[str, Any]:
    now = datetime.now(UTC)
    action = ApprovalAction(
        id=str(uuid4()),
        post_id=post_id,
        revision=revision,
        transport=source,
        status="created",
        selected_action=None,
        remote_ref=None,
        created_at=_utc_iso(now),
        expires_at=_utc_iso(now + timedelta(hours=72)),
        consumed_at=None,
        last_error=None,
    )
    with write_session() as session:
        post = session.get(Post, post_id)
        if post is None:
            raise AppError("Draft not found.", 404)
        if post.revision != revision:
            raise AppError("This draft changed. Send the latest revision for approval.")
        if post.status != "pending":
            raise AppError(f"Only pending drafts can be sent for approval. Current status: {post.status}.")
        session.add(action)
    return {
        "id": action.id,
        "postId": action.post_id,
        "revision": action.revision,
        "transport": action.transport,
        "expiresAt": action.expires_at,
    }


def record_approval_sent(action_id: str, remote_ref: str | None = None) -> None:
    with write_session() as session:
        action = session.get(ApprovalAction, action_id)
        if action is None or action.status != "created":
            raise AppError("Approval request is no longer available.")
        action.status = "sent"
        action.remote_ref = remote_ref
        channel = "Slack" if action.transport == "slack" else "Telegram"
        _append_audit(
            session,
            action="approval.sent",
            entity_type="post",
            entity_id=action.post_id,
            summary=f"Revision {action.revision} approval request sent to {channel}; expires in 72 hours.",
        )


def fail_approval_delivery(action_id: str, message: str) -> None:
    with write_session() as session:
        action = session.get(ApprovalAction, action_id)
        if action is None or action.status != "created":
            return
        action.status = "failed"
        action.last_error = message[:2_000]
        action.consumed_at = utc_now()


def post_for_approval(post_id: str, revision: int) -> dict[str, Any]:
    with read_session() as session:
        post = session.get(Post, post_id)
        if post is None:
            raise AppError("Draft not found.", 404)
        if post.revision != revision:
            raise AppError("This draft changed. Send the latest revision for approval.")
        if post.status != "pending":
            raise AppError(f"Only pending drafts can be sent for approval. Current status: {post.status}.")
        return _post_dict(post)


def _supersede_approval_actions(
    session: Session,
    post_id: str,
    revision: int,
    *,
    except_id: str | None = None,
) -> None:
    actions = session.scalars(
        select(ApprovalAction).where(
            ApprovalAction.post_id == post_id,
            ApprovalAction.revision == revision,
            ApprovalAction.status.in_(("created", "sent")),
        )
    ).all()
    now = utc_now()
    for action in actions:
        if action.id == except_id:
            continue
        action.status = "superseded"
        action.consumed_at = now


def edit_post(post_id: str, payload: EditPostRequest) -> None:
    with write_session() as session:
        post = session.get(Post, post_id)
        if post is None:
            raise AppError("Draft not found.", 404)
        if post.revision != payload.revision:
            raise AppError("This draft changed. Reopen the latest revision before saving.")
        if post.status == "published":
            raise AppError("Published content is immutable. Create a new draft instead.")
        if post.status == "publishing":
            raise AppError("This draft is currently being published.")
        if post.channel == "instagram" and not payload.media_url:
            raise AppError("Instagram drafts require a public image URL.")
        if payload.media_asset_id is not None and session.get(MediaAsset, str(payload.media_asset_id)) is None:
            raise AppError("Selected media asset no longer exists.", 404)
        post.title = payload.title
        post.body = payload.body
        post.hashtags = payload.hashtags
        if payload.call_to_action is not None:
            post.call_to_action = payload.call_to_action
        if payload.image_prompt is not None:
            post.image_prompt = payload.image_prompt
        if payload.image_negative_prompt is not None:
            post.image_negative_prompt = payload.image_negative_prompt
        if payload.image_alt_text is not None:
            post.image_alt_text = payload.image_alt_text
        post.media_asset_id = str(payload.media_asset_id) if payload.media_asset_id else None
        post.media_url = payload.media_url or None
        previous_revision = post.revision
        post.status = "pending"
        post.revision += 1
        post.approved_at = None
        post.published_at = None
        post.remote_id = None
        post.remote_url = None
        post.updated_at = utc_now()
        post.last_error = None
        _supersede_approval_actions(session, post.id, previous_revision)
        _cancel_pending_post_jobs(session, post.id, "Draft edited; scheduled publish cancelled.")
        _append_audit(
            session,
            action="post.edited",
            entity_type="post",
            entity_id=post.id,
            summary="Draft edited; prior approval invalidated.",
        )


def decide_post(
    post_id: str,
    revision: int,
    decision: Literal["approve", "skip"],
    source: str = "dashboard",
) -> None:
    with write_session() as session:
        post = session.get(Post, post_id)
        if post is None:
            raise AppError("Draft not found.", 404)
        if post.revision != revision:
            raise AppError("This draft changed. Review the latest revision before deciding.")
        if post.status != "pending":
            raise AppError(f"Only pending drafts can be decided. Current status: {post.status}.")
        approved = decision == "approve"
        post.status = "approved" if approved else "skipped"
        post.approved_at = utc_now() if approved else None
        post.updated_at = utc_now()
        post.last_error = None
        _supersede_approval_actions(session, post.id, revision)
        if approved:
            _queue_approved_automation_publish(session, post)
        if not approved:
            _cancel_pending_post_jobs(session, post.id, "Draft skipped; scheduled publish cancelled.")
        external_source = source if source in {"telegram", "slack"} else None
        suffix = f".{external_source}" if external_source else ""
        source_label = external_source.title() if external_source else None
        _append_audit(
            session,
            action=f"post.{'approved' if approved else 'skipped'}{suffix}",
            entity_type="post",
            entity_id=post.id,
            summary=(
                f"Revision {revision} {'approved' if approved else 'skipped'} from {source_label}."
                if source_label
                else "Draft approved and version locked."
                if approved
                else "Draft skipped without publication."
            ),
        )


def post_for_regeneration(post_id: str, revision: int) -> dict[str, Any]:
    with read_session() as session:
        post = session.get(Post, post_id)
        if post is None:
            raise AppError("Draft not found.", 404)
        if post.revision != revision:
            raise AppError("This draft changed. Regenerate the latest revision instead.")
        if post.status != "pending":
            raise AppError(f"Only pending drafts can be regenerated. Current status: {post.status}.")
        return _post_dict(post)


def finish_post_regeneration(
    post_id: str,
    revision: int,
    *,
    content: dict[str, Any],
    provider: dict[str, str],
    brand_profile_version: int,
    source: str = "dashboard",
    approval_action_id: str | None = None,
) -> dict[str, Any]:
    with write_session() as session:
        post = session.get(Post, post_id)
        if post is None:
            raise AppError("Draft not found.", 404)
        if post.revision != revision or post.status != "pending":
            raise AppError("This draft changed while regeneration was running. Review the latest revision.")
        if approval_action_id:
            action = session.get(ApprovalAction, approval_action_id)
            if (
                action is None
                or action.status != "processing"
                or action.selected_action not in {"regenerate", "regenerate_post"}
            ):
                raise AppError("This regeneration action is no longer active.")
            action.status = "consumed"
            action.consumed_at = utc_now()
        post.title = content["title"]
        post.body = content["body"]
        post.hashtags = content.get("hashtags", [])
        post.call_to_action = content.get("call_to_action", "")
        post.image_prompt = content.get("image_prompt", "")
        post.image_negative_prompt = content.get("image_negative_prompt", "")
        post.image_alt_text = content.get("image_alt_text", "")
        post.rationale = content.get("rationale", "")
        post.provider_kind = provider["kind"]
        post.model = provider["model"]
        post.brand_profile_version = brand_profile_version
        post.revision += 1
        post.status = "pending"
        post.approved_at = None
        post.updated_at = utc_now()
        post.last_error = None
        _supersede_approval_actions(session, post.id, revision, except_id=approval_action_id)
        _cancel_pending_post_jobs(session, post.id, "Draft regenerated; scheduled publish cancelled.")
        _append_audit(
            session,
            action=f"post.regenerated{'.' + source if source in {'telegram', 'slack'} else ''}",
            entity_type="post",
            entity_id=post.id,
            summary=f"Revision {revision} regenerated as revision {post.revision}; fresh approval required.",
        )
        return _post_dict(post)


def finish_image_regeneration(
    post_id: str,
    revision: int,
    *,
    media_asset_id: str,
    source: str = "dashboard",
    approval_action_id: str | None = None,
) -> dict[str, Any]:
    with write_session() as session:
        post = session.get(Post, post_id)
        asset = session.get(MediaAsset, media_asset_id)
        if post is None:
            raise AppError("Draft not found.", 404)
        if asset is None:
            raise AppError("The regenerated image could not be found.", 404)
        if post.revision != revision or post.status != "pending":
            raise AppError("This draft changed while image regeneration was running.")
        if approval_action_id:
            action = session.get(ApprovalAction, approval_action_id)
            if (
                action is None
                or action.status != "processing"
                or action.selected_action != "regenerate_image"
            ):
                raise AppError("This image regeneration action is no longer active.")
            action.status = "consumed"
            action.consumed_at = utc_now()
        post.media_asset_id = media_asset_id
        post.image_alt_text = asset.alt_text or post.image_alt_text
        post.revision += 1
        post.status = "pending"
        post.approved_at = None
        post.updated_at = utc_now()
        post.last_error = None
        _supersede_approval_actions(session, post.id, revision, except_id=approval_action_id)
        _cancel_pending_post_jobs(
            session, post.id, "Image regenerated; scheduled publish cancelled."
        )
        suffix = f".{source}" if source in {"telegram", "slack"} else ""
        _append_audit(
            session,
            action=f"post.image_regenerated{suffix}",
            entity_type="post",
            entity_id=post.id,
            summary=(
                f"Image for revision {revision} regenerated as revision {post.revision}; "
                "fresh approval required."
            ),
        )
        return _post_dict(post)


def claim_remote_approval_action(
    action_id: str,
    selected_action: Literal[
        "approve", "regenerate", "regenerate_post", "regenerate_image", "edit", "skip"
    ],
    source: Literal["telegram", "slack"],
) -> dict[str, Any]:
    error: AppError | None = None
    result: dict[str, Any] | None = None
    with write_session() as session:
        action = session.get(ApprovalAction, action_id)
        if action is None or action.transport != source:
            error = AppError("Unknown or mismatched Socium approval action.")
        elif action.status != "sent":
            post = session.get(Post, action.post_id)
            same_revision = post is not None and post.revision == action.revision
            same_terminal_decision = (
                selected_action == "approve"
                and post is not None
                and post.status in {"approved", "publishing", "published"}
            ) or (
                selected_action == "skip" and post is not None and post.status == "skipped"
            )
            if same_revision and same_terminal_decision:
                # Slack and Telegram can carry separate buttons for the same revision.
                # Treat the later matching decision as a successful replay. The first
                # transaction already changed the post and (when applicable) created
                # the uniquely-keyed publish job, so no side effect is repeated here.
                action.selected_action = selected_action
                action.consumed_at = action.consumed_at or utc_now()
                result = _post_dict(post)
                result["approvalReplay"] = True
            else:
                error = AppError("This approval action was already used or is no longer active.")
        elif datetime.fromisoformat(action.expires_at) <= datetime.now(UTC):
            action.status = "expired"
            action.consumed_at = utc_now()
            error = AppError("This approval request expired. Send the latest revision again.")
        else:
            post = session.get(Post, action.post_id)
            if post is None:
                action.status = "invalid"
                action.consumed_at = utc_now()
                error = AppError("Draft no longer exists.")
            elif post.revision != action.revision:
                action.status = "superseded"
                action.consumed_at = utc_now()
                error = AppError("Stale action: review the latest draft revision.")
            elif post.status != "pending":
                action.status = "superseded"
                action.consumed_at = utc_now()
                error = AppError(f"Draft is already {post.status}.")
            else:
                action.selected_action = selected_action
                action.consumed_at = utc_now()
                if selected_action in {"regenerate", "regenerate_post", "regenerate_image"}:
                    action.status = "processing"
                    result = _post_dict(post)
                elif selected_action == "edit":
                    action.status = "consumed"
                    _set_metadata(
                        session,
                        "remote_edit_request",
                        json.dumps(
                            {
                                "id": action.id,
                                "postId": post.id,
                                "revision": post.revision,
                                "source": source,
                                "createdAt": action.consumed_at,
                            },
                            separators=(",", ":"),
                        ),
                    )
                    _append_audit(
                        session,
                        action=f"post.edit_requested.{source}",
                        entity_type="post",
                        entity_id=post.id,
                        summary=f"Revision {post.revision} opened for editing from {source.title()}.",
                    )
                    result = _post_dict(post)
                else:
                    approved = selected_action == "approve"
                    action.status = "consumed"
                    post.status = "approved" if approved else "skipped"
                    post.approved_at = utc_now() if approved else None
                    post.updated_at = utc_now()
                    post.last_error = None
                    _supersede_approval_actions(session, post.id, post.revision, except_id=action.id)
                    if approved:
                        _queue_approved_automation_publish(session, post)
                    if not approved:
                        _cancel_pending_post_jobs(
                            session, post.id, "Draft skipped; scheduled publish cancelled."
                        )
                    _append_audit(
                        session,
                        action=f"post.{'approved' if approved else 'skipped'}.{source}",
                        entity_type="post",
                        entity_id=post.id,
                        summary=f"Revision {post.revision} {'approved and locked' if approved else 'skipped'} from {source.title()}.",
                    )
                    result = _post_dict(post)
    if error is not None:
        raise error
    if result is None:
        raise AppError("Approval action could not be applied.")
    return result


def fail_remote_regeneration(action_id: str, message: str) -> None:
    with write_session() as session:
        action = session.get(ApprovalAction, action_id)
        if action is None or action.status != "processing":
            return
        action.status = "failed"
        action.last_error = message[:2_000]


def acknowledge_remote_edit(action_id: str) -> None:
    with write_session() as session:
        metadata = session.get(AppMetadata, "remote_edit_request")
        if metadata is None:
            return
        try:
            request = json.loads(metadata.value)
        except (TypeError, ValueError, json.JSONDecodeError):
            request = {}
        if request.get("id") == action_id:
            session.delete(metadata)


def process_telegram_update(update: dict[str, Any]) -> dict[str, str] | None:
    update_id = update.get("update_id")
    if not isinstance(update_id, int):
        return None
    with write_session() as session:
        telegram = session.get(TelegramSettings, 1)
        if telegram is None or update_id <= telegram.last_update_id:
            return None
        telegram.last_update_id = update_id
        callback = update.get("callback_query")
        if not isinstance(callback, dict) or not isinstance(callback.get("data"), str):
            return None
        callback_id = str(callback.get("id") or "")
        data = callback["data"].split(":")
        if len(data) != 3 or data[0] != "sa" or data[1] not in {"a", "r", "p", "i", "e", "s"}:
            return {"callbackId": callback_id, "error": "Unknown Socium action."} if callback_id else None

        message = callback.get("message")
        chat = message.get("chat") if isinstance(message, dict) else None
        callback_chat = chat.get("id") if isinstance(chat, dict) else None
        if telegram.chat_id.lstrip("-").isdigit() and str(callback_chat) != telegram.chat_id:
            return (
                {"callbackId": callback_id, "error": "This chat is not authorized for Socium approvals."}
                if callback_id
                else None
            )
        action_names = {
            "a": "approve",
            "r": "regenerate_post",
            "p": "regenerate_post",
            "i": "regenerate_image",
            "e": "edit",
            "s": "skip",
        }
        message_id = message.get("message_id") if isinstance(message, dict) else None
        message_text = (
            message.get("text") or message.get("caption") if isinstance(message, dict) else None
        )
        if not callback_id:
            return None
        parsed = {
            "callbackId": callback_id,
            "actionId": data[2],
            "action": action_names[data[1]],
        }
        if callback_chat is not None and message_id is not None:
            parsed.update(
                {
                    "chatId": str(callback_chat),
                    "messageId": str(message_id),
                    "messageText": str(message_text) if isinstance(message_text, str) else "",
                    "hasPhoto": bool(message.get("photo")) if isinstance(message, dict) else False,
                }
            )
        return parsed


def reserve_publish(post_id: str, revision: int) -> dict[str, Any]:
    with write_session() as session:
        post = session.get(Post, post_id)
        if post is None:
            raise AppError("Draft not found.", 404)
        if post.revision != revision:
            raise AppError("This draft changed. Review the latest revision before publishing.")
        if post.status != "approved":
            raise AppError("Approve this exact draft version before publishing.")
        if post.channel not in PUBLISHER_NAMES:
            raise AppError(f"{post.channel} publisher is not installed yet.")
        publisher = publisher_name(post.channel)
        post.status = "publishing"
        post.updated_at = utc_now()
        post.last_error = None
        snapshot = _post_dict(post)
        _append_audit(
            session,
            action="post.publish_reserved",
            entity_type="publisher",
            entity_id=post.id,
            summary=f"{publisher} publish reserved for revision {post.revision}.",
        )
        return snapshot


def finish_publish(
    post_id: str,
    revision: int,
    remote_id: str,
    remote_url: str | None = None,
) -> None:
    with write_session() as session:
        post = session.get(Post, post_id)
        if post is None or post.revision != revision or post.status != "publishing":
            raise AppError("Publish reservation no longer matches the current draft.")
        post.status = "published"
        post.published_at = utc_now()
        post.updated_at = post.published_at
        post.remote_id = remote_id
        post.remote_url = remote_url[:2_048] if remote_url else None
        post.last_error = None
        _cancel_pending_post_jobs(session, post.id, "Draft already published; redundant job cancelled.")
        _append_audit(
            session,
            action="post.published",
            entity_type="publisher",
            entity_id=post.id,
            summary=(
                f"Revision {post.revision} published to {publisher_name(post.channel)} "
                f"as remote item {remote_id}."
            ),
        )


def fail_publish(post_id: str, revision: int, message: str) -> None:
    with write_session() as session:
        post = session.get(Post, post_id)
        if post is None or post.revision != revision or post.status != "publishing":
            return
        post.status = "approved"
        post.last_error = message[:2_000]
        post.updated_at = utc_now()
        _append_audit(
            session,
            action="post.publish_failed",
            entity_type="publisher",
            entity_id=post.id,
            summary=f"{publisher_name(post.channel)} publish failed for revision {post.revision}.",
        )


def fail_publish_uncertain(post_id: str, revision: int, message: str) -> None:
    with write_session() as session:
        post = session.get(Post, post_id)
        if post is None or post.revision != revision or post.status != "publishing":
            return
        post.status = "failed"
        post.last_error = message[:2_000]
        post.updated_at = utc_now()
        _append_audit(
            session,
            action="post.publish_uncertain",
            entity_type="publisher",
            entity_id=post.id,
            summary=(
                f"{publisher_name(post.channel)} delivery failed after reservation; automatic retry was "
                "blocked to prevent duplicates."
            ),
        )


def _cancel_pending_post_jobs(session: Session, post_id: str, summary: str) -> None:
    jobs = list(
        session.scalars(
            select(LocalJob).where(
                LocalJob.kind == "post.publish",
                LocalJob.status.in_({"queued", "retrying"}),
            )
        ).all()
    )
    now = utc_now()
    for job in jobs:
        if str((job.payload or {}).get("post_id")) != post_id:
            continue
        job.status = "cancelled"
        job.completed_at = now
        job.updated_at = now
        job.last_error = summary


def scheduler_paused() -> bool:
    with read_session() as session:
        metadata = session.get(AppMetadata, "scheduler_paused")
        return metadata is not None and metadata.value == "true"


def set_scheduler_paused(paused: bool) -> None:
    with write_session() as session:
        metadata = session.get(AppMetadata, "scheduler_paused")
        if metadata is None:
            session.add(AppMetadata(key="scheduler_paused", value="true" if paused else "false"))
        else:
            metadata.value = "true" if paused else "false"
        _append_audit(
            session,
            action="scheduler.paused" if paused else "scheduler.resumed",
            entity_type="scheduler",
            entity_id="local",
            summary="Local scheduler paused." if paused else "Local scheduler resumed.",
        )
    if not paused:
        mark_overdue_jobs_for_recovery(
            "The local worker was paused at the scheduled time. Choose Run now, Reschedule, or Skip."
        )


def _mark_overdue_jobs_for_recovery(session: Session, reason: str) -> int:
    now = utc_now()
    jobs = list(
        session.scalars(
            select(LocalJob).where(
                LocalJob.kind == "post.publish",
                LocalJob.status.in_({"queued", "retrying"}),
                LocalJob.run_at < now,
            )
        ).all()
    )
    for job in jobs:
        job.status = "missed"
        job.locked_at = None
        job.lease_token = None
        job.lease_expires_at = None
        job.completed_at = None
        job.recovery_required_at = now
        job.recovery_reason = reason[:500]
        job.last_error = job.recovery_reason
        job.updated_at = now
        _append_audit(
            session,
            action="job.recovery_required",
            entity_type="scheduler",
            entity_id=job.id,
            summary=job.recovery_reason,
        )
    return len(jobs)


def mark_overdue_jobs_for_recovery(reason: str) -> int:
    with write_session() as session:
        return _mark_overdue_jobs_for_recovery(session, reason)


def recovery_pending_count() -> int:
    with read_session() as session:
        return len(
            session.scalars(
                select(LocalJob.id).where(
                    LocalJob.kind == "post.publish",
                    LocalJob.status == "missed",
                    LocalJob.recovery_required_at.is_not(None),
                )
            ).all()
        )


def pending_approval_action_count(transport: Literal["telegram", "slack"]) -> int:
    with read_session() as session:
        return len(
            session.scalars(
                select(ApprovalAction.id).where(
                    ApprovalAction.transport == transport,
                    ApprovalAction.status == "sent",
                    ApprovalAction.expires_at > utc_now(),
                )
            ).all()
        )


def _next_automation_occurrence(
    timezone: str,
    days_of_week: list[int],
    publish_time: str,
    *,
    after: datetime | None = None,
) -> datetime:
    zone = ZoneInfo(timezone)
    cursor = (after or datetime.now(UTC)).astimezone(zone)
    hour, minute = (int(part) for part in publish_time.split(":", 1))
    for offset in range(15):
        candidate_date = cursor.date() + timedelta(days=offset)
        if candidate_date.weekday() not in days_of_week:
            continue
        candidate = datetime.combine(candidate_date, time(hour, minute), tzinfo=zone)
        if candidate > cursor:
            return candidate.astimezone(UTC)
    raise AppError("Could not calculate the next automation run.")


def _cancel_automation_jobs(session: Session, automation_id: str, summary: str) -> None:
    generation_jobs = session.scalars(
        select(LocalJob).where(
            LocalJob.kind == "automation.generate",
            LocalJob.status.in_({"queued", "retrying"}),
        )
    ).all()
    post_ids = set(
        session.scalars(select(Post.id).where(Post.automation_id == automation_id)).all()
    )
    publish_jobs = session.scalars(
        select(LocalJob).where(
            LocalJob.kind == "post.publish",
            LocalJob.status.in_({"queued", "retrying"}),
        )
    ).all()
    now = utc_now()
    for job in generation_jobs:
        if str((job.payload or {}).get("automation_id") or "") != automation_id:
            continue
        job.status = "cancelled"
        job.completed_at = now
        job.updated_at = now
        job.last_error = summary
    for job in publish_jobs:
        if str((job.payload or {}).get("post_id") or "") not in post_ids:
            continue
        job.status = "cancelled"
        job.completed_at = now
        job.updated_at = now
        job.last_error = summary


def _queue_approved_automation_publish(session: Session, post: Post) -> bool:
    if not post.automation_id or not post.automation_publish_at:
        return False
    rule = session.get(AutomationRule, post.automation_id)
    if rule is None or not rule.publish_after_approval:
        return False
    key = f"post.publish:{post.id}:{post.revision}"
    if session.scalar(select(LocalJob).where(LocalJob.idempotency_key == key)) is not None:
        return False
    publish_at = datetime.fromisoformat(post.automation_publish_at)
    run_at = max(datetime.now(UTC), publish_at)
    now = utc_now()
    session.add(
        LocalJob(
            id=str(uuid4()),
            idempotency_key=key,
            kind="post.publish",
            status="queued",
            payload={"post_id": post.id, "revision": post.revision, "channel": post.channel},
            run_at=_utc_iso(run_at),
            attempts=0,
            max_attempts=3,
            locked_at=None,
            completed_at=None,
            last_error=None,
            created_at=now,
            updated_at=now,
        )
    )
    _append_audit(
        session,
        action="automation.publish_queued",
        entity_type="automation",
        entity_id=post.automation_id,
        summary=f"Approved revision {post.revision} queued for its automation publish time.",
    )
    return True


def _queue_automation_occurrence(
    session: Session,
    rule: AutomationRule,
    *,
    after: datetime | None = None,
) -> LocalJob:
    occurrence = _next_automation_occurrence(
        rule.timezone,
        list(rule.days_of_week or []),
        rule.publish_time,
        after=after,
    )
    now = datetime.now(UTC)
    run_at = max(now, occurrence - timedelta(minutes=rule.generate_ahead_minutes))
    occurrence_iso = _utc_iso(occurrence)
    key = f"automation.generate:{rule.id}:{occurrence_iso}"
    existing = session.scalar(select(LocalJob).where(LocalJob.idempotency_key == key))
    if existing is not None:
        if existing.status not in {"queued", "retrying", "running"}:
            existing.status = "queued"
            existing.payload = {"automation_id": rule.id, "publish_at": occurrence_iso}
            existing.run_at = _utc_iso(run_at)
            existing.attempts = 0
            existing.locked_at = None
            existing.lease_token = None
            existing.lease_expires_at = None
            existing.recovery_required_at = None
            existing.recovery_reason = None
            existing.completed_at = None
            existing.last_error = None
            existing.progress_percent = 0
            existing.progress_message = None
            existing.cancel_requested = False
            existing.remote_ref = None
            existing.result_ref = None
            existing.updated_at = utc_now()
        rule.next_run_at = existing.run_at
        rule.next_publish_at = occurrence_iso
        return existing
    created_at = utc_now()
    job = LocalJob(
        id=str(uuid4()),
        idempotency_key=key,
        kind="automation.generate",
        status="queued",
        payload={"automation_id": rule.id, "publish_at": occurrence_iso},
        run_at=_utc_iso(run_at),
        attempts=0,
        max_attempts=3,
        locked_at=None,
        completed_at=None,
        last_error=None,
        created_at=created_at,
        updated_at=created_at,
    )
    session.add(job)
    rule.next_run_at = job.run_at
    rule.next_publish_at = occurrence_iso
    return job


def create_automation(payload: AutomationRuleUpsert) -> dict[str, Any]:
    now = utc_now()
    with write_session() as session:
        rule = AutomationRule(
            id=str(uuid4()),
            name=payload.name,
            enabled=payload.enabled,
            channel=payload.channel,
            topic=payload.topic,
            tone=payload.tone,
            objective=payload.objective,
            timezone=payload.timezone,
            days_of_week=payload.days_of_week,
            publish_time=payload.publish_time,
            approval_channels=payload.approval_channels,
            generate_ahead_minutes=payload.generate_ahead_minutes,
            publish_after_approval=payload.publish_after_approval,
            next_run_at=None,
            next_publish_at=None,
            last_run_at=None,
            last_error=None,
            created_at=now,
            updated_at=now,
        )
        session.add(rule)
        session.flush()
        if rule.enabled:
            _queue_automation_occurrence(session, rule)
        _append_audit(
            session,
            action="automation.created",
            entity_type="automation",
            entity_id=rule.id,
            summary=f"Created {rule.name} with {len(rule.days_of_week)} post slots per week.",
        )
        session.flush()
        return _automation_dict(rule)


def update_automation(automation_id: str, payload: AutomationRuleUpsert) -> dict[str, Any]:
    with write_session() as session:
        rule = session.get(AutomationRule, automation_id)
        if rule is None:
            raise AppError("Automation not found.", 404)
        material_change = any(
            (
                rule.enabled != payload.enabled,
                rule.channel != payload.channel,
                rule.topic != payload.topic,
                rule.tone != payload.tone,
                rule.objective != payload.objective,
                rule.timezone != payload.timezone,
                list(rule.days_of_week or []) != payload.days_of_week,
                rule.publish_time != payload.publish_time,
                list(rule.approval_channels or []) != payload.approval_channels,
                rule.generate_ahead_minutes != payload.generate_ahead_minutes,
                rule.publish_after_approval != payload.publish_after_approval,
            )
        )
        if material_change:
            _cancel_automation_jobs(session, rule.id, "Automation schedule changed or paused.")
        rule.name = payload.name
        rule.enabled = payload.enabled
        rule.channel = payload.channel
        rule.topic = payload.topic
        rule.tone = payload.tone
        rule.objective = payload.objective
        rule.timezone = payload.timezone
        rule.days_of_week = payload.days_of_week
        rule.publish_time = payload.publish_time
        rule.approval_channels = payload.approval_channels
        rule.generate_ahead_minutes = payload.generate_ahead_minutes
        rule.publish_after_approval = payload.publish_after_approval
        if material_change:
            rule.next_run_at = None
            rule.next_publish_at = None
            rule.last_error = None
        rule.updated_at = utc_now()
        if rule.enabled and (material_change or not rule.next_run_at):
            _queue_automation_occurrence(session, rule)
        _append_audit(
            session,
            action="automation.updated",
            entity_type="automation",
            entity_id=rule.id,
            summary=f"Updated {rule.name}; {len(rule.days_of_week)} post slots per week.",
        )
        session.flush()
        return _automation_dict(rule)


def delete_automation(automation_id: str) -> None:
    with write_session() as session:
        rule = session.get(AutomationRule, automation_id)
        if rule is None:
            raise AppError("Automation not found.", 404)
        name = rule.name
        _cancel_automation_jobs(session, rule.id, "Automation deleted.")
        for post in session.scalars(select(Post).where(Post.automation_id == rule.id)).all():
            post.automation_id = None
        session.delete(rule)
        _append_audit(
            session,
            action="automation.deleted",
            entity_type="automation",
            entity_id=automation_id,
            summary=f"Deleted {name}. Existing drafts and published history were preserved.",
        )


def duplicate_automation(automation_id: str) -> dict[str, Any]:
    with read_session() as session:
        rule = session.get(AutomationRule, automation_id)
        if rule is None:
            raise AppError("Automation not found.", 404)
        payload = AutomationRuleUpsert(
            name=f"{rule.name} copy"[:120],
            enabled=False,
            channel=rule.channel,
            topic=rule.topic,
            tone=rule.tone,
            objective=rule.objective,
            timezone=rule.timezone,
            days_of_week=list(rule.days_of_week or []),
            publish_time=rule.publish_time,
            approval_channels=list(rule.approval_channels or []),
            generate_ahead_minutes=rule.generate_ahead_minutes,
            publish_after_approval=rule.publish_after_approval,
        )
    return create_automation(payload)


def automation_runtime(automation_id: str) -> dict[str, Any]:
    with read_session() as session:
        rule = session.get(AutomationRule, automation_id)
        if rule is None or not rule.enabled:
            raise AppError("This automation is disabled or no longer exists.")
        return _automation_dict(rule)


def complete_automation_occurrence(automation_id: str, occurrence_at: str) -> dict[str, Any]:
    with write_session() as session:
        rule = session.get(AutomationRule, automation_id)
        if rule is None:
            raise AppError("Automation not found.", 404)
        now = utc_now()
        rule.last_run_at = now
        rule.last_error = None
        rule.updated_at = now
        rule.next_run_at = None
        rule.next_publish_at = None
        if rule.enabled:
            after = datetime.fromisoformat(occurrence_at)
            _queue_automation_occurrence(session, rule, after=after)
        _append_audit(
            session,
            action="automation.generated",
            entity_type="automation",
            entity_id=rule.id,
            summary=f"{rule.name} generated its scheduled draft.",
        )
        session.flush()
        return _automation_dict(rule)


def fail_automation_occurrence(automation_id: str, message: str) -> None:
    with write_session() as session:
        rule = session.get(AutomationRule, automation_id)
        if rule is None:
            return
        rule.last_error = message[:2_000]
        rule.updated_at = utc_now()


def ensure_automation_jobs() -> int:
    created = 0
    with write_session() as session:
        rules = session.scalars(select(AutomationRule).where(AutomationRule.enabled.is_(True))).all()
        for rule in rules:
            active = False
            for job in session.scalars(
                select(LocalJob).where(
                    LocalJob.kind == "automation.generate",
                    LocalJob.status.in_({"queued", "retrying", "running"}),
                )
            ).all():
                if str((job.payload or {}).get("automation_id") or "") == rule.id:
                    active = True
                    rule.next_run_at = job.run_at
                    rule.next_publish_at = str((job.payload or {}).get("publish_at") or "") or None
                    break
            if not active:
                _queue_automation_occurrence(session, rule)
                created += 1
    return created


def schedule_post(
    post_id: str, payload: SchedulePostRequest, catch_up_hours: int
) -> tuple[dict[str, Any], bool]:
    now = datetime.now(UTC)
    if payload.run_at < now - timedelta(hours=catch_up_hours):
        raise AppError(f"Scheduled time is outside the {catch_up_hours}-hour catch-up window.")
    if payload.run_at > now + timedelta(days=366):
        raise AppError("Scheduled time must be within the next year.")
    key = f"post.publish:{post_id}:{payload.revision}"
    with write_session() as session:
        existing = session.scalar(select(LocalJob).where(LocalJob.idempotency_key == key))
        if existing is not None:
            return _job_dict(existing), False
        post = session.get(Post, post_id)
        if post is None:
            raise AppError("Draft not found.", 404)
        if post.revision != payload.revision:
            raise AppError("This draft changed. Review the latest revision before scheduling.")
        if post.status != "approved":
            raise AppError("Approve this exact draft version before scheduling.")
        if post.channel not in PUBLISHER_NAMES:
            raise AppError(f"{post.channel} scheduler is not installed yet.")
        publisher = publisher_name(post.channel)
        created_at = utc_now()
        job = LocalJob(
            id=str(uuid4()),
            idempotency_key=key,
            kind="post.publish",
            status="queued",
            payload={"post_id": post.id, "revision": post.revision, "channel": post.channel},
            run_at=_utc_iso(payload.run_at),
            attempts=0,
            max_attempts=3,
            locked_at=None,
            completed_at=None,
            last_error=None,
            created_at=created_at,
            updated_at=created_at,
        )
        session.add(job)
        _append_audit(
            session,
            action="job.scheduled",
            entity_type="scheduler",
            entity_id=job.id,
            summary=f"{publisher} publish scheduled for revision {post.revision} at {job.run_at}.",
        )
        session.flush()
        return _job_dict(job), True


def cancel_job(job_id: str) -> dict[str, Any]:
    with write_session() as session:
        job = session.get(LocalJob, job_id)
        if job is None:
            raise AppError("Scheduled job not found.", 404)
        if job.status not in {"queued", "retrying"}:
            raise AppError(f"Only queued jobs can be cancelled. Current status: {job.status}.")
        now = utc_now()
        job.status = "cancelled"
        job.completed_at = now
        job.updated_at = now
        job.last_error = "Cancelled by the local operator."
        _append_audit(
            session,
            action="job.cancelled",
            entity_type="scheduler",
            entity_id=job.id,
            summary="Scheduled publish cancelled by the local operator.",
        )
        return _job_dict(job)


def retry_job(job_id: str) -> dict[str, Any]:
    with write_session() as session:
        job = session.get(LocalJob, job_id)
        if job is None:
            raise AppError("Scheduled job not found.", 404)
        if job.status != "failed":
            raise AppError(f"Only failed jobs can be retried here. Current status: {job.status}.")
        post_id = str((job.payload or {}).get("post_id") or "")
        revision = int((job.payload or {}).get("revision") or 0)
        post = session.get(Post, post_id)
        if post is None or post.revision != revision:
            raise AppError("The scheduled draft no longer matches this job.")
        if post.status == "published":
            raise AppError("This draft is already published; retry was blocked.")
        if post.status not in {"approved", "failed"}:
            raise AppError(f"Draft must be approved before retrying. Current status: {post.status}.")
        if post.status == "failed":
            post.status = "approved"
            post.last_error = None
            post.updated_at = utc_now()
        now = utc_now()
        job.status = "queued"
        job.run_at = now
        job.attempts = 0
        job.locked_at = None
        job.lease_token = None
        job.lease_expires_at = None
        job.recovery_required_at = None
        job.recovery_reason = None
        job.completed_at = None
        job.last_error = None
        job.updated_at = now
        _append_audit(
            session,
            action="job.retried",
            entity_type="scheduler",
            entity_id=job.id,
            summary="Failed scheduled publish explicitly requeued by the local operator.",
        )
        return _job_dict(job)


def recover_missed_job(job_id: str, payload: JobRecoveryRequest) -> dict[str, Any]:
    with write_session() as session:
        job = session.get(LocalJob, job_id)
        if job is None or job.kind != "post.publish":
            raise AppError("Scheduled publish not found.", 404)
        if job.status != "missed" or not job.recovery_required_at:
            raise AppError(f"This job does not require recovery. Current status: {job.status}.")

        post_id = str((job.payload or {}).get("post_id") or "")
        revision = int((job.payload or {}).get("revision") or 0)
        post = session.get(Post, post_id)
        if payload.decision != "skip":
            if post is None or post.revision != revision:
                raise AppError("The scheduled draft changed or no longer exists. Skip this stale job.")
            if post.status == "published":
                raise AppError("This exact draft is already published; duplicate recovery was blocked.")
            if post.status not in {"approved", "failed"}:
                raise AppError(f"Draft must still be approved. Current status: {post.status}.")

        now_dt = datetime.now(UTC)
        now = _utc_iso(now_dt)
        if payload.decision == "reschedule":
            assert payload.run_at is not None
            if payload.run_at <= now_dt:
                raise AppError("Choose a future time when rescheduling.")
            if payload.run_at > now_dt + timedelta(days=366):
                raise AppError("Rescheduled time must be within the next year.")
            job.status = "queued"
            job.run_at = _utc_iso(payload.run_at)
            action = "job.recovery_rescheduled"
            summary = f"Missed publish rescheduled for {job.run_at}."
        elif payload.decision == "run_now":
            job.status = "queued"
            job.run_at = now
            action = "job.recovery_run_now"
            summary = "Operator confirmed that the missed publish should run now."
        else:
            job.status = "skipped"
            job.completed_at = now
            action = "job.recovery_skipped"
            summary = "Operator skipped the missed publish; nothing was sent."

        if payload.decision != "skip":
            job.completed_at = None
            job.last_error = None
            if post is not None and post.status == "failed":
                post.status = "approved"
                post.last_error = None
                post.updated_at = now
        else:
            job.last_error = "Skipped by the local operator after restart recovery."
        job.locked_at = None
        job.lease_token = None
        job.lease_expires_at = None
        job.recovery_required_at = None
        job.recovery_reason = None
        job.updated_at = now
        _append_audit(
            session,
            action=action,
            entity_type="scheduler",
            entity_id=job.id,
            summary=summary,
        )
        return _job_dict(job)


def recover_stale_jobs(stale_minutes: int) -> int:
    cutoff = _utc_iso(datetime.now(UTC) - timedelta(minutes=stale_minutes))
    now_iso = utc_now()
    with write_session() as session:
        jobs = list(
            session.scalars(
                select(LocalJob).where(
                    LocalJob.status == "running",
                    or_(
                        LocalJob.lease_expires_at < now_iso,
                        and_(LocalJob.lease_expires_at.is_(None), LocalJob.locked_at < cutoff),
                    ),
                )
            ).all()
        )
        now = utc_now()
        for job in jobs:
            post_id = str((job.payload or {}).get("post_id") or "")
            post = session.get(Post, post_id)
            if job.kind == "post.publish" and post is not None and post.status == "publishing":
                job.status = "failed"
                job.completed_at = now
                job.last_error = (
                    "Delivery state is uncertain after an interrupted publish; review before retrying."
                )
                post.status = "failed"
                post.last_error = job.last_error
                post.updated_at = now
            elif job.attempts < job.max_attempts:
                job.status = "queued"
                job.run_at = now
                job.last_error = "Recovered after an interrupted local worker."
            else:
                job.status = "failed"
                job.completed_at = now
                job.last_error = "The local worker stopped before this job could finish."
            job.locked_at = None
            job.lease_token = None
            job.lease_expires_at = None
            job.updated_at = now
            _append_audit(
                session,
                action="job.recovered" if job.status == "queued" else "job.failed",
                entity_type="scheduler",
                entity_id=job.id,
                summary=job.last_error,
            )
        return len(jobs)


def next_job_run_at() -> str | None:
    with read_session() as session:
        return session.scalar(
            select(LocalJob.run_at)
            .where(LocalJob.status.in_({"queued", "retrying"}))
            .order_by(LocalJob.run_at.asc())
            .limit(1)
        )


def claim_due_job(lease_seconds: int = 360) -> dict[str, Any] | None:
    with write_session() as session:
        metadata = session.get(AppMetadata, "scheduler_paused")
        if metadata is not None and metadata.value == "true":
            return None
        job = session.scalar(
            select(LocalJob)
            .where(LocalJob.status.in_({"queued", "retrying"}), LocalJob.run_at <= utc_now())
            .order_by(LocalJob.run_at.asc(), LocalJob.created_at.asc())
            .limit(1)
        )
        if job is None:
            return None
        now = utc_now()
        lease_token = str(uuid4())
        job.status = "running"
        job.attempts += 1
        job.locked_at = now
        job.lease_token = lease_token
        job.lease_expires_at = _utc_iso(datetime.now(UTC) + timedelta(seconds=lease_seconds))
        job.updated_at = now
        job.last_error = None
        if job.kind == "media.generate":
            job.progress_percent = max(job.progress_percent, 5)
            job.progress_message = "Local image worker started."
        session.flush()
        claimed = _job_dict(job)
        claimed["leaseToken"] = lease_token
        return claimed


def _lease_matches(job: LocalJob, lease_token: str | None) -> bool:
    return lease_token is None or bool(job.lease_token and job.lease_token == lease_token)


def complete_job(job_id: str, lease_token: str | None = None) -> bool:
    with write_session() as session:
        job = session.get(LocalJob, job_id)
        if job is None or job.status != "running" or not _lease_matches(job, lease_token):
            return False
        now = utc_now()
        job.status = "completed"
        job.completed_at = now
        job.locked_at = None
        job.lease_token = None
        job.lease_expires_at = None
        job.updated_at = now
        job.last_error = None
        _append_audit(
            session,
            action="job.completed",
            entity_type="scheduler",
            entity_id=job.id,
            summary="Scheduled local job completed.",
        )
        return True


def fail_job(
    job_id: str,
    message: str,
    *,
    retryable: bool,
    lease_token: str | None = None,
) -> bool:
    with write_session() as session:
        job = session.get(LocalJob, job_id)
        if job is None or job.status != "running" or not _lease_matches(job, lease_token):
            return False
        now = datetime.now(UTC)
        if retryable and job.attempts < job.max_attempts:
            delay_seconds = min(60, 5 * (2 ** max(job.attempts - 1, 0)))
            job.status = "retrying"
            job.run_at = _utc_iso(now + timedelta(seconds=delay_seconds))
            action = "job.retry_scheduled"
            summary = (
                f"Job retry {job.attempts + 1}/{job.max_attempts} scheduled after a local preflight failure."
            )
        else:
            job.status = "failed"
            job.completed_at = _utc_iso(now)
            action = "job.failed"
            summary = "Scheduled local job failed and requires review."
        job.locked_at = None
        job.lease_token = None
        job.lease_expires_at = None
        job.updated_at = _utc_iso(now)
        job.last_error = message[:2_000]
        if job.kind == "media.generate":
            job.progress_message = (
                "Generation will retry automatically."
                if job.status == "retrying"
                else "Generation failed; review the error and retry when ready."
            )
        _append_audit(
            session,
            action=action,
            entity_type="scheduler",
            entity_id=job.id,
            summary=summary,
        )
        return True


def publish_reservation_active(post_id: str, revision: int) -> bool:
    with read_session() as session:
        post = session.get(Post, post_id)
        return bool(post is not None and post.revision == revision and post.status == "publishing")
