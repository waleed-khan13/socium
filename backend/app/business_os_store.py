from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from app.database import read_session, write_session
from app.errors import AppError
from app.models import (
    AIDecisionLog,
    ApprovalAction,
    ApprovalRequestRecord,
    AuditEvent,
    AutomationRule,
    BusinessProfile,
    ConnectorAccount,
    InboxItem,
    KnowledgeItem,
    KnowledgeSource,
    Lead,
    LocalJob,
    Post,
    ProviderSettings,
    TelegramSettings,
    WorkflowDefinition,
    WorkflowRun,
    WorkflowStep,
    Workspace,
)
from app.schemas import (
    GenericApprovalDecision,
    InboxItemUpdate,
    KnowledgeItemUpdate,
    KnowledgeSourceCreate,
    WorkflowDefinitionCreate,
    WorkflowRunCreate,
)


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _workspace_facts(workspace: Workspace) -> dict[str, Any]:
    return {
        "workspaceName": workspace.name,
        "businessName": workspace.business_name,
        "description": workspace.description,
        "timezone": workspace.timezone,
        "website": workspace.website,
        "industry": workspace.industry,
        "productsServices": workspace.products_services,
        "targetAudience": workspace.target_audience,
        "location": workspace.location,
        "goals": workspace.goals or [],
        "callToAction": workspace.call_to_action,
        "language": workspace.language,
        "tone": workspace.tone,
        "contentPillars": workspace.content_pillars or [],
        "restrictedClaims": workspace.restricted_claims or [],
        "brandedHashtags": workspace.branded_hashtags or [],
    }


def _workspace_visual_profile(workspace: Workspace) -> dict[str, Any]:
    return {
        "logoMediaId": workspace.logo_media_id,
        "referenceMediaIds": workspace.reference_media_ids or [],
        "primaryColor": workspace.primary_color,
        "secondaryColor": workspace.secondary_color,
        "accentColor": workspace.accent_color,
        "headingFont": workspace.heading_font,
        "bodyFont": workspace.body_font,
        "visualStyle": workspace.visual_style,
    }


def _ensure_business_profile(session: Session, workspace_id: int = 1) -> BusinessProfile:
    workspace = session.get(Workspace, workspace_id)
    if workspace is None:
        raise AppError("Workspace not found.", 404)
    profile = session.scalar(
        select(BusinessProfile).where(BusinessProfile.workspace_id == workspace_id)
    )
    if profile is None:
        now = utc_now()
        profile = BusinessProfile(
            id=str(uuid4()),
            workspace_id=workspace_id,
            revision=max(workspace.profile_version, 1),
            status="confirmed" if workspace.confirmed_at else "draft",
            facts=_workspace_facts(workspace),
            visual_profile=_workspace_visual_profile(workspace),
            confirmed_at=workspace.confirmed_at,
            created_at=now,
            updated_at=workspace.updated_at or now,
        )
        session.add(profile)
    elif workspace.updated_at and profile.updated_at < workspace.updated_at:
        profile.revision = max(workspace.profile_version, profile.revision)
        profile.status = "confirmed" if workspace.confirmed_at else "draft"
        profile.facts = _workspace_facts(workspace)
        profile.visual_profile = _workspace_visual_profile(workspace)
        profile.confirmed_at = workspace.confirmed_at
        profile.updated_at = workspace.updated_at
    return profile


def _profile_dict(profile: BusinessProfile) -> dict[str, Any]:
    return {
        "id": profile.id,
        "workspaceId": profile.workspace_id,
        "revision": profile.revision,
        "status": profile.status,
        "facts": profile.facts or {},
        "visualProfile": profile.visual_profile or {},
        "confirmedAt": profile.confirmed_at,
        "createdAt": profile.created_at,
        "updatedAt": profile.updated_at,
    }


def business_profile(workspace_id: int = 1) -> dict[str, Any]:
    with write_session() as session:
        return _profile_dict(_ensure_business_profile(session, workspace_id))


def _source_dict(source: KnowledgeSource) -> dict[str, Any]:
    return {
        "id": source.id,
        "workspaceId": source.workspace_id,
        "kind": source.kind,
        "locator": source.locator,
        "title": source.title,
        "status": source.status,
        "checksum": source.checksum,
        "lastCheckedAt": source.last_checked_at,
        "lastError": source.last_error,
        "createdAt": source.created_at,
        "updatedAt": source.updated_at,
    }


def _item_dict(item: KnowledgeItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "workspaceId": item.workspace_id,
        "sourceId": item.source_id,
        "factKey": item.fact_key,
        "value": item.value,
        "confidence": item.confidence,
        "status": item.status,
        "sourceExcerpt": item.source_excerpt,
        "verifiedAt": item.verified_at,
        "createdAt": item.created_at,
        "updatedAt": item.updated_at,
    }


def create_knowledge_source(payload: KnowledgeSourceCreate) -> dict[str, Any]:
    now = utc_now()
    with write_session() as session:
        _ensure_business_profile(session, payload.workspace_id)
        existing = session.scalar(
            select(KnowledgeSource).where(
                KnowledgeSource.workspace_id == payload.workspace_id,
                KnowledgeSource.kind == payload.kind,
                KnowledgeSource.locator == payload.locator,
            )
        )
        if existing is not None:
            existing.title = payload.title or existing.title
            existing.updated_at = now
            return _source_dict(existing)
        source = KnowledgeSource(
            id=str(uuid4()),
            workspace_id=payload.workspace_id,
            kind=payload.kind,
            locator=payload.locator,
            title=payload.title,
            status="pending",
            created_at=now,
            updated_at=now,
        )
        session.add(source)
        session.flush()
        return _source_dict(source)


def record_knowledge_analysis(
    *,
    workspace_id: int,
    url: str,
    draft: dict[str, Any],
    field_origins: dict[str, str],
    sources: list[dict[str, str]],
) -> dict[str, Any]:
    now = utc_now()
    encoded = json.dumps({"draft": draft, "sources": sources}, sort_keys=True).encode("utf-8")
    checksum = hashlib.sha256(encoded).hexdigest()
    with write_session() as session:
        profile = _ensure_business_profile(session, workspace_id)
        source = session.scalar(
            select(KnowledgeSource).where(
                KnowledgeSource.workspace_id == workspace_id,
                KnowledgeSource.kind == "website",
                KnowledgeSource.locator == url,
            )
        )
        if source is None:
            source = KnowledgeSource(
                id=str(uuid4()),
                workspace_id=workspace_id,
                kind="website",
                locator=url,
                title=(sources[0].get("title") if sources else "") or url,
                status="ready",
                checksum=checksum,
                last_checked_at=now,
                created_at=now,
                updated_at=now,
            )
            session.add(source)
            session.flush()
        else:
            source.status = "ready"
            source.checksum = checksum
            source.last_checked_at = now
            source.last_error = None
            source.updated_at = now
        session.execute(
            delete(KnowledgeItem).where(
                KnowledgeItem.source_id == source.id,
                KnowledgeItem.status.in_(("proposed", "rejected", "stale")),
            )
        )
        created: list[KnowledgeItem] = []
        source_urls = ", ".join(item.get("url", "") for item in sources[:4] if item.get("url"))
        for key, raw_value in draft.items():
            if raw_value in (None, "", []):
                continue
            value = json.dumps(raw_value, ensure_ascii=False) if isinstance(raw_value, (list, dict)) else str(raw_value)
            origin = field_origins.get(key, "not-found")
            confidence = 90 if origin == "website" else 65 if origin == "website-suggestion" else 45
            existing_confirmed = session.scalar(
                select(KnowledgeItem).where(
                    KnowledgeItem.workspace_id == workspace_id,
                    KnowledgeItem.fact_key == key,
                    KnowledgeItem.status == "confirmed",
                )
            )
            if existing_confirmed is not None and existing_confirmed.value == value:
                existing_confirmed.source_id = source.id
                existing_confirmed.verified_at = now
                existing_confirmed.updated_at = now
                continue
            if existing_confirmed is not None:
                existing_confirmed.status = "stale"
                existing_confirmed.updated_at = now
            item = KnowledgeItem(
                id=str(uuid4()),
                workspace_id=workspace_id,
                source_id=source.id,
                fact_key=key,
                value=value,
                confidence=confidence,
                status="proposed",
                source_excerpt=source_urls[:2_000],
                created_at=now,
                updated_at=now,
            )
            session.add(item)
            created.append(item)
        profile.updated_at = now
        session.add(
            AuditEvent(
                id=str(uuid4()),
                action="knowledge.website.analyzed",
                entity_type="knowledge",
                entity_id=source.id,
                summary=f"Analyzed {url} and prepared {len(created)} facts for review.",
                created_at=now,
            )
        )
        session.flush()
        return {"source": _source_dict(source), "items": [_item_dict(item) for item in created]}


def knowledge_state(
    workspace_id: int = 1,
    *,
    status: str | None = None,
    query: str | None = None,
) -> dict[str, Any]:
    with read_session() as session:
        sources = list(
            session.scalars(
                select(KnowledgeSource)
                .where(KnowledgeSource.workspace_id == workspace_id)
                .order_by(KnowledgeSource.updated_at.desc())
            ).all()
        )
        item_query = select(KnowledgeItem).where(KnowledgeItem.workspace_id == workspace_id)
        if status:
            item_query = item_query.where(KnowledgeItem.status == status)
        if query and query.strip():
            ids = session.execute(
                text(
                    "SELECT knowledge_items.id FROM knowledge_items_fts "
                    "JOIN knowledge_items ON knowledge_items_fts.rowid = knowledge_items.rowid "
                    "WHERE knowledge_items_fts MATCH :query AND knowledge_items.workspace_id = :workspace_id "
                    "ORDER BY bm25(knowledge_items_fts) LIMIT 100"
                ),
                {"query": query.strip().replace('"', '""'), "workspace_id": workspace_id},
            ).scalars().all()
            item_query = item_query.where(KnowledgeItem.id.in_(ids or ["__none__"]))
        items = list(session.scalars(item_query.order_by(KnowledgeItem.updated_at.desc())).all())
        return {
            "sources": [_source_dict(source) for source in sources],
            "items": [_item_dict(item) for item in items],
            "summary": {
                "total": len(items),
                "confirmed": sum(item.status == "confirmed" for item in items),
                "needsReview": sum(item.status in {"proposed", "stale"} for item in items),
            },
        }


def update_knowledge_item(item_id: str, payload: KnowledgeItemUpdate) -> dict[str, Any]:
    now = utc_now()
    with write_session() as session:
        item = session.get(KnowledgeItem, item_id)
        if item is None:
            raise AppError("Knowledge fact not found.", 404)
        if payload.value is not None:
            item.value = payload.value
        if payload.status is not None:
            item.status = payload.status
            item.verified_at = now if payload.status == "confirmed" else None
        item.updated_at = now
        if item.status == "confirmed":
            profile = _ensure_business_profile(session, item.workspace_id)
            facts = dict(profile.facts or {})
            try:
                confirmed_value: Any = json.loads(item.value)
            except json.JSONDecodeError:
                confirmed_value = item.value
            facts[item.fact_key] = confirmed_value
            visual_keys = {
                "logoMediaId",
                "referenceMediaIds",
                "primaryColor",
                "secondaryColor",
                "accentColor",
                "headingFont",
                "bodyFont",
                "visualStyle",
            }
            if item.fact_key in visual_keys:
                visual = dict(profile.visual_profile or {})
                visual[item.fact_key] = confirmed_value
                profile.visual_profile = visual
            else:
                profile.facts = facts
            profile.revision += 1
            profile.updated_at = now
            workspace = session.get(Workspace, item.workspace_id)
            workspace_fields = {
                "workspaceName": "name",
                "businessName": "business_name",
                "description": "description",
                "timezone": "timezone",
                "website": "website",
                "industry": "industry",
                "productsServices": "products_services",
                "targetAudience": "target_audience",
                "location": "location",
                "goals": "goals",
                "callToAction": "call_to_action",
                "language": "language",
                "tone": "tone",
                "contentPillars": "content_pillars",
                "restrictedClaims": "restricted_claims",
                "brandedHashtags": "branded_hashtags",
                "logoMediaId": "logo_media_id",
                "referenceMediaIds": "reference_media_ids",
                "primaryColor": "primary_color",
                "secondaryColor": "secondary_color",
                "accentColor": "accent_color",
                "headingFont": "heading_font",
                "bodyFont": "body_font",
                "visualStyle": "visual_style",
            }
            field_name = workspace_fields.get(item.fact_key)
            if workspace is not None and field_name:
                setattr(workspace, field_name, confirmed_value)
                workspace.updated_at = now
        session.add(
            AuditEvent(
                id=str(uuid4()),
                action=f"knowledge.fact.{item.status}",
                entity_type="knowledge",
                entity_id=item.id,
                summary=f"Marked {item.fact_key} as {item.status}.",
                created_at=now,
            )
        )
        return _item_dict(item)


def delete_knowledge_source(source_id: str) -> None:
    with write_session() as session:
        source = session.get(KnowledgeSource, source_id)
        if source is None:
            raise AppError("Knowledge source not found.", 404)
        session.execute(delete(KnowledgeItem).where(KnowledgeItem.source_id == source.id))
        session.delete(source)


def _workflow_dict(workflow: WorkflowDefinition) -> dict[str, Any]:
    return {
        "id": workflow.id,
        "workspaceId": workflow.workspace_id,
        "name": workflow.name,
        "kind": workflow.kind,
        "enabled": workflow.enabled,
        "approvalMode": workflow.approval_mode,
        "config": workflow.config or {},
        "createdAt": workflow.created_at,
        "updatedAt": workflow.updated_at,
    }


def list_workflows(workspace_id: int = 1) -> list[dict[str, Any]]:
    with read_session() as session:
        workflows = list(
            session.scalars(
                select(WorkflowDefinition)
                .where(WorkflowDefinition.workspace_id == workspace_id)
                .order_by(WorkflowDefinition.created_at.desc())
            ).all()
        )
        legacy = list(session.scalars(select(AutomationRule).order_by(AutomationRule.created_at.desc())).all())
        return [_workflow_dict(item) for item in workflows] + [
            {
                "id": item.id,
                "workspaceId": workspace_id,
                "name": item.name,
                "kind": "social.schedule",
                "enabled": item.enabled,
                "approvalMode": "approval_required" if item.approval_channels else "auto_with_rules",
                "config": {"legacyAutomation": True, "channel": item.channel},
                "createdAt": item.created_at,
                "updatedAt": item.updated_at,
            }
            for item in legacy
        ]


def create_workflow(payload: WorkflowDefinitionCreate) -> dict[str, Any]:
    now = utc_now()
    with write_session() as session:
        _ensure_business_profile(session, payload.workspace_id)
        workflow = WorkflowDefinition(
            id=str(uuid4()),
            workspace_id=payload.workspace_id,
            name=payload.name,
            kind=payload.kind,
            enabled=payload.enabled,
            approval_mode=payload.approval_mode,
            config=payload.config,
            created_at=now,
            updated_at=now,
        )
        session.add(workflow)
        session.flush()
        return _workflow_dict(workflow)


def _approval_dict(approval: ApprovalRequestRecord) -> dict[str, Any]:
    return {
        "id": approval.id,
        "workspaceId": approval.workspace_id,
        "subjectType": approval.subject_type,
        "subjectId": approval.subject_id,
        "subjectRevision": approval.subject_revision,
        "status": approval.status,
        "allowedActions": approval.allowed_actions or [],
        "decidedAction": approval.decided_action,
        "decidedBy": approval.decided_by,
        "decisionSource": approval.decision_source,
        "expiresAt": approval.expires_at,
        "decidedAt": approval.decided_at,
        "createdAt": approval.created_at,
        "updatedAt": approval.updated_at,
    }


def run_workflow(workflow_id: str, payload: WorkflowRunCreate) -> dict[str, Any]:
    now = utc_now()
    with write_session() as session:
        workflow = session.get(WorkflowDefinition, workflow_id)
        if workflow is None:
            raise AppError("Workflow not found.", 404)
        if not workflow.enabled:
            raise AppError("Enable this workflow before running it.")
        run = WorkflowRun(
            id=str(uuid4()),
            workspace_id=workflow.workspace_id,
            workflow_id=workflow.id,
            trigger=payload.trigger,
            status="waiting_approval" if workflow.approval_mode != "full_auto" else "completed",
            input_data=payload.input_data,
            output_data={"message": "Workflow proposal validated locally."},
            started_at=now,
            completed_at=now if workflow.approval_mode == "full_auto" else None,
            created_at=now,
            updated_at=now,
        )
        session.add(run)
        session.add(
            WorkflowStep(
                id=str(uuid4()),
                run_id=run.id,
                position=1,
                kind="policy.validate",
                status="completed",
                input_data=payload.input_data,
                output_data={"safe": True},
                started_at=now,
                completed_at=now,
            )
        )
        approval: ApprovalRequestRecord | None = None
        if workflow.approval_mode != "full_auto":
            approval = ApprovalRequestRecord(
                id=str(uuid4()),
                workspace_id=workflow.workspace_id,
                subject_type="workflow_run",
                subject_id=run.id,
                subject_revision=1,
                status="pending",
                allowed_actions=["approve", "edit", "reject", "skip", "reschedule"],
                expires_at=(datetime.now(UTC) + timedelta(days=7)).isoformat().replace("+00:00", "Z"),
                created_at=now,
                updated_at=now,
            )
            session.add(approval)
            session.add(
                InboxItem(
                    id=str(uuid4()),
                    workspace_id=workflow.workspace_id,
                    kind="approval",
                    priority="normal",
                    status="open",
                    title=f"Approve {workflow.name}",
                    body="A deterministic workflow proposal is waiting for your decision.",
                    entity_type="approval_request",
                    entity_id=approval.id,
                    action_url="/?view=approvals",
                    metadata_json={"workflowRunId": run.id},
                    dedupe_key=f"approval:{approval.id}",
                    created_at=now,
                    updated_at=now,
                )
            )
        session.flush()
        return {
            "id": run.id,
            "workflowId": workflow.id,
            "status": run.status,
            "trigger": run.trigger,
            "createdAt": run.created_at,
            "approval": _approval_dict(approval) if approval else None,
        }


def list_approvals(workspace_id: int = 1, status: str | None = None) -> list[dict[str, Any]]:
    with read_session() as session:
        query = select(ApprovalRequestRecord).where(ApprovalRequestRecord.workspace_id == workspace_id)
        if status:
            query = query.where(ApprovalRequestRecord.status == status)
        generic = list(session.scalars(query.order_by(ApprovalRequestRecord.created_at.desc())).all())
        legacy_query = select(ApprovalAction).order_by(ApprovalAction.created_at.desc())
        legacy = list(session.scalars(legacy_query).all())
        mapped_legacy = [
            {
                "id": item.id,
                "workspaceId": workspace_id,
                "subjectType": "post",
                "subjectId": item.post_id,
                "subjectRevision": item.revision,
                "status": "pending" if item.status in {"created", "sent", "processing"} else item.status,
                "allowedActions": ["approve", "edit", "regenerate_text", "regenerate_image", "reject", "skip"],
                "decidedAction": item.selected_action,
                "decidedBy": None,
                "decisionSource": item.transport,
                "expiresAt": item.expires_at,
                "decidedAt": item.consumed_at,
                "createdAt": item.created_at,
                "updatedAt": item.consumed_at or item.created_at,
                "legacy": True,
            }
            for item in legacy
            if status is None or (status == "pending" and item.status in {"created", "sent", "processing"}) or item.status == status
        ]
        return [_approval_dict(item) for item in generic] + mapped_legacy


def decide_approval(approval_id: str, payload: GenericApprovalDecision) -> dict[str, Any]:
    now = utc_now()
    with write_session() as session:
        approval = session.get(ApprovalRequestRecord, approval_id)
        if approval is None:
            raise AppError("Approval request not found.", 404)
        if approval.status != "pending":
            result = _approval_dict(approval)
            result["duplicate"] = True
            return result
        if payload.action not in (approval.allowed_actions or []):
            raise AppError("That action is not allowed for this approval.")
        approval.status = "approved" if payload.action == "approve" else payload.action
        approval.decided_action = payload.action
        approval.decided_by = payload.actor
        approval.decision_source = payload.source
        approval.decided_at = now
        approval.updated_at = now
        if approval.subject_type == "workflow_run":
            run = session.get(WorkflowRun, approval.subject_id)
            if run is not None:
                run.status = "approved" if payload.action == "approve" else payload.action
                run.completed_at = now
                run.updated_at = now
        inbox = session.scalar(
            select(InboxItem).where(InboxItem.dedupe_key == f"approval:{approval.id}")
        )
        if inbox is not None:
            inbox.status = "resolved"
            inbox.resolved_at = now
            inbox.updated_at = now
        return _approval_dict(approval)


def _inbox_dict(item: InboxItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "workspaceId": item.workspace_id,
        "kind": item.kind,
        "priority": item.priority,
        "status": item.status,
        "title": item.title,
        "body": item.body,
        "entityType": item.entity_type,
        "entityId": item.entity_id,
        "actionUrl": item.action_url,
        "metadata": item.metadata_json or {},
        "resolvedAt": item.resolved_at,
        "createdAt": item.created_at,
        "updatedAt": item.updated_at,
    }


def list_inbox(workspace_id: int = 1, status: str | None = "open") -> list[dict[str, Any]]:
    with read_session() as session:
        query = select(InboxItem).where(InboxItem.workspace_id == workspace_id)
        if status:
            query = query.where(InboxItem.status == status)
        stored = list(session.scalars(query.order_by(InboxItem.created_at.desc())).all())
        dynamic: list[dict[str, Any]] = []
        for post in session.scalars(select(Post).where(Post.status == "pending").limit(50)).all():
            dynamic.append(
                {
                    "id": f"post:{post.id}:{post.revision}",
                    "workspaceId": workspace_id,
                    "kind": "approval",
                    "priority": "normal",
                    "status": "open",
                    "title": f"Review {post.title or post.topic[:80]}",
                    "body": f"{post.channel.title()} draft revision {post.revision} is waiting for approval.",
                    "entityType": "post",
                    "entityId": post.id,
                    "actionUrl": "/?view=approvals",
                    "metadata": {"revision": post.revision, "channel": post.channel},
                    "resolvedAt": None,
                    "createdAt": post.created_at,
                    "updatedAt": post.updated_at,
                }
            )
        for job in session.scalars(
            select(LocalJob).where(LocalJob.status.in_(("failed", "missed"))).limit(50)
        ).all():
            dynamic.append(
                {
                    "id": f"job:{job.id}",
                    "workspaceId": workspace_id,
                    "kind": "missed_schedule" if job.status == "missed" else "workflow_failure",
                    "priority": "high",
                    "status": "open",
                    "title": "Scheduled work needs attention" if job.status == "missed" else "Workflow failed",
                    "body": job.recovery_reason or job.last_error or "Open the scheduler for recovery options.",
                    "entityType": "job",
                    "entityId": job.id,
                    "actionUrl": "/?view=calendar",
                    "metadata": {"jobStatus": job.status},
                    "resolvedAt": None,
                    "createdAt": job.created_at,
                    "updatedAt": job.updated_at,
                }
            )
        combined = [_inbox_dict(item) for item in stored] + dynamic
        return sorted(combined, key=lambda item: item["createdAt"], reverse=True)


def update_inbox_item(item_id: str, payload: InboxItemUpdate) -> dict[str, Any]:
    now = utc_now()
    with write_session() as session:
        item = session.get(InboxItem, item_id)
        if item is None:
            raise AppError("Inbox item not found or is derived from live system state.", 404)
        item.status = payload.status
        item.resolved_at = now if payload.status in {"resolved", "dismissed"} else None
        item.updated_at = now
        return _inbox_dict(item)


def record_ai_decision(
    *,
    purpose: str,
    provider_kind: str,
    model: str,
    status: str,
    duration_ms: int | None,
    context_refs: list[dict[str, Any]] | None = None,
    error: str | None = None,
    workspace_id: int = 1,
) -> None:
    with write_session() as session:
        session.add(
            AIDecisionLog(
                id=str(uuid4()),
                workspace_id=workspace_id,
                purpose=purpose[:80],
                provider_kind=provider_kind[:40],
                model=model[:180],
                prompt_version="content-kit-v1" if purpose == "content.generate" else "business-os-v1",
                context_refs=context_refs or [],
                status=status[:30],
                duration_ms=duration_ms,
                error=error[:4_000] if error else None,
                created_at=utc_now(),
            )
        )


def list_ai_decisions(workspace_id: int = 1, limit: int = 100) -> list[dict[str, Any]]:
    with read_session() as session:
        items = session.scalars(
            select(AIDecisionLog)
            .where(AIDecisionLog.workspace_id == workspace_id)
            .order_by(AIDecisionLog.created_at.desc())
            .limit(min(max(limit, 1), 500))
        ).all()
        return [
            {
                "id": item.id,
                "purpose": item.purpose,
                "providerKind": item.provider_kind,
                "model": item.model,
                "promptVersion": item.prompt_version,
                "contextRefs": item.context_refs or [],
                "status": item.status,
                "durationMs": item.duration_ms,
                "inputTokens": item.input_tokens,
                "outputTokens": item.output_tokens,
                "estimatedCostMicros": item.estimated_cost_micros,
                "error": item.error,
                "createdAt": item.created_at,
            }
            for item in items
        ]


def dashboard_summary(workspace_id: int = 1) -> dict[str, Any]:
    with read_session() as session:
        workspace = session.get(Workspace, workspace_id)
        if workspace is None:
            raise AppError("Workspace not found.", 404)
        provider = session.get(ProviderSettings, 1)
        telegram = session.get(TelegramSettings, 1)
        posts = list(session.scalars(select(Post).order_by(Post.created_at.desc())).all())
        jobs = list(session.scalars(select(LocalJob).order_by(LocalJob.created_at.desc())).all())
        leads = session.scalar(select(func.count()).select_from(Lead)) or 0
        connectors = list(
            session.scalars(
                select(ConnectorAccount)
                .where(ConnectorAccount.enabled.is_(True))
                .order_by(ConnectorAccount.adapter_id)
            ).all()
        )
        knowledge_review = session.scalar(
            select(func.count())
            .select_from(KnowledgeItem)
            .where(
                KnowledgeItem.workspace_id == workspace_id,
                KnowledgeItem.status.in_(("proposed", "stale")),
            )
        ) or 0
        pending = sum(post.status == "pending" for post in posts)
        failed = sum(job.status in {"failed", "missed"} for job in jobs)
        upcoming = sorted(
            [post for post in posts if post.automation_publish_at and post.status not in {"published", "rejected", "skipped"}],
            key=lambda post: post.automation_publish_at or "",
        )[:6]
        today = datetime.now(UTC).date()
        trend: dict[str, int] = {}
        for offset in range(29, -1, -1):
            trend[(today - timedelta(days=offset)).isoformat()] = 0
        for post in posts:
            if not post.published_at:
                continue
            day = post.published_at[:10]
            if day in trend:
                trend[day] += 1
        activity = list(
            session.scalars(select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(8)).all()
        )
        return {
            "workspace": {
                "id": workspace.id,
                "name": workspace.name,
                "businessName": workspace.business_name,
            },
            "attention": {
                "total": pending + failed + knowledge_review,
                "pendingApprovals": pending,
                "failedWorkflows": failed,
                "knowledgeReview": knowledge_review,
            },
            "metrics": {
                "postsPublished": sum(post.status == "published" for post in posts),
                "postsScheduled": len(upcoming),
                "approvalsPending": pending,
                "leadsCaptured": int(leads),
                "failedWorkflows": failed,
            },
            "publishingTrend": [{"date": day, "value": value} for day, value in trend.items()],
            "engagement": {"available": False, "reason": "Connect an analytics provider to see reach and engagement."},
            "ai": {
                "configured": bool(provider and provider.base_url and provider.model),
                "kind": provider.kind if provider else "ollama",
                "model": provider.model if provider else "",
                "local": bool(provider and provider.kind == "ollama"),
            },
            "channels": [
                {
                    "id": item.id,
                    "adapterId": item.adapter_id,
                    "name": item.name,
                    "status": item.status,
                    "connected": item.status == "verified",
                }
                for item in connectors
            ]
            + ([{"id": "telegram", "adapterId": "telegram", "name": "Telegram", "status": "verified", "connected": True}] if telegram and telegram.chat_id and telegram.bot_token else []),
            "upcoming": [
                {
                    "id": post.id,
                    "title": post.title,
                    "channel": post.channel,
                    "status": post.status,
                    "publishAt": post.automation_publish_at,
                    "mediaAssetId": post.media_asset_id,
                }
                for post in upcoming
            ],
            "recentActivity": [
                {
                    "id": event.id,
                    "action": event.action,
                    "summary": event.summary,
                    "entityType": event.entity_type,
                    "entityId": event.entity_id,
                    "createdAt": event.created_at,
                }
                for event in activity
            ],
            "generatedAt": utc_now(),
        }
