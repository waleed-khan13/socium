from __future__ import annotations

import csv
import io
import json
from typing import Any
from uuid import uuid4

from sqlalchemy import select

from app.database import read_session, write_session
from app.errors import AppError
from app.growth_store import advance_campaign_after_export_in_session
from app.lead_store import _lead_dict, outreach_state
from app.models import Company, Contact, Lead, OutreachDraft
from app.schemas import (
    GeneratedOutreach,
    LeadDeleteRequest,
    OutreachDecisionRequest,
    OutreachDraftUpdate,
    OutreachGenerateRequest,
)
from app.store import append_audit, utc_now


def _draft_dict(draft: OutreachDraft) -> dict[str, object]:
    return {
        "id": draft.id,
        "leadId": draft.lead_id,
        "revision": draft.revision,
        "channel": draft.channel,
        "objective": draft.objective,
        "tone": draft.tone,
        "subject": draft.subject,
        "body": draft.body,
        "rationale": draft.rationale,
        "status": draft.status,
        "providerKind": draft.provider_kind,
        "model": draft.model,
        "createdAt": draft.created_at,
        "updatedAt": draft.updated_at,
        "approvedAt": draft.approved_at,
        "exportedAt": draft.exported_at,
    }


def _require_ready(lead: Lead) -> None:
    state = outreach_state(lead)
    if not state["outreachReady"]:
        blockers = state["outreachBlockers"]
        message = (
            str(blockers[0]) if isinstance(blockers, list) and blockers else "Lead is not outreach-ready."
        )
        raise AppError(message)


def outreach_generation_context(lead_id: str) -> dict[str, object]:
    with read_session() as session:
        lead = session.get(Lead, lead_id)
        if lead is None:
            raise AppError("Lead not found.", 404)
        _require_ready(lead)
        return _lead_dict(lead)


def list_outreach_drafts(lead_id: str) -> dict[str, object]:
    with read_session() as session:
        if session.get(Lead, lead_id) is None:
            raise AppError("Lead not found.", 404)
        drafts = list(
            session.scalars(
                select(OutreachDraft)
                .where(OutreachDraft.lead_id == lead_id)
                .order_by(OutreachDraft.created_at.desc())
            ).all()
        )
        return {"items": [_draft_dict(draft) for draft in drafts]}


def create_outreach_draft(
    lead_id: str,
    payload: OutreachGenerateRequest,
    generated: GeneratedOutreach,
    provider: dict[str, str],
) -> dict[str, object]:
    with write_session() as session:
        lead = session.get(Lead, lead_id)
        if lead is None:
            raise AppError("Lead not found.", 404)
        _require_ready(lead)
        now = utc_now()
        draft = OutreachDraft(
            id=str(uuid4()),
            lead_id=lead.id,
            revision=1,
            channel="email",
            objective=payload.objective,
            tone=payload.tone,
            subject=generated.subject,
            body=generated.body,
            rationale=generated.rationale,
            status="draft",
            provider_kind=provider["kind"],
            model=provider["model"],
            created_at=now,
            updated_at=now,
            approved_at=None,
            exported_at=None,
        )
        session.add(draft)
        append_audit(
            session,
            action="outreach.draft_generated",
            entity_type="outreach",
            entity_id=draft.id,
            summary="AI outreach draft generated for human review; no message was sent.",
        )
        return _draft_dict(draft)


def edit_outreach_draft(draft_id: str, payload: OutreachDraftUpdate) -> dict[str, object]:
    with write_session() as session:
        draft = session.get(OutreachDraft, draft_id)
        if draft is None:
            raise AppError("Outreach draft not found.", 404)
        draft.subject = payload.subject
        draft.body = payload.body
        draft.revision += 1
        draft.status = "draft"
        draft.approved_at = None
        draft.exported_at = None
        draft.updated_at = utc_now()
        append_audit(
            session,
            action="outreach.draft_edited",
            entity_type="outreach",
            entity_id=draft.id,
            summary=f"Outreach draft edited; revision {draft.revision} requires a new review.",
        )
        return _draft_dict(draft)


def decide_outreach_draft(draft_id: str, payload: OutreachDecisionRequest) -> dict[str, object]:
    with write_session() as session:
        draft = session.get(OutreachDraft, draft_id)
        if draft is None:
            raise AppError("Outreach draft not found.", 404)
        if draft.revision != payload.revision:
            raise AppError("This draft changed. Review the latest revision before deciding.")
        draft.status = "approved" if payload.decision == "approve" else "rejected"
        draft.approved_at = utc_now() if payload.decision == "approve" else None
        draft.exported_at = None
        draft.updated_at = utc_now()
        append_audit(
            session,
            action=f"outreach.draft_{payload.decision}d",
            entity_type="outreach",
            entity_id=draft.id,
            summary=f"Outreach draft revision {draft.revision} {payload.decision}d by the operator.",
        )
        return _draft_dict(draft)


def _safe_csv_cell(value: object) -> str:
    text = str(value or "")
    return f"'{text}" if text.startswith(("=", "+", "-", "@")) else text


def export_outreach_draft(draft_id: str, revision: int) -> dict[str, object]:
    with write_session() as session:
        draft = session.get(OutreachDraft, draft_id)
        if draft is None:
            raise AppError("Outreach draft not found.", 404)
        if draft.revision != revision:
            raise AppError("This export request references an older draft revision.")
        if draft.status not in {"approved", "exported"}:
            raise AppError("Approve the current draft revision before exporting it.")
        lead = session.get(Lead, draft.lead_id)
        if lead is None:
            raise AppError("Lead not found.", 404)
        _require_ready(lead)
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(
            [
                "lead_id",
                "business_name",
                "email",
                "subject",
                "body",
                "legal_basis",
                "consent_status",
                "retention_until",
                "source_ref",
            ]
        )
        writer.writerow(
            [
                _safe_csv_cell(lead.id),
                _safe_csv_cell(lead.business_name),
                _safe_csv_cell(lead.email),
                _safe_csv_cell(draft.subject),
                _safe_csv_cell(draft.body),
                _safe_csv_cell(lead.legal_basis),
                _safe_csv_cell(lead.consent_status),
                _safe_csv_cell(lead.retention_until),
                _safe_csv_cell(lead.source_ref),
            ]
        )
        now = utc_now()
        draft.status = "exported"
        draft.exported_at = now
        draft.updated_at = now
        advance_campaign_after_export_in_session(session, draft.id)
        append_audit(
            session,
            action="outreach.draft_exported",
            entity_type="outreach",
            entity_id=draft.id,
            summary=f"Approved outreach draft revision {draft.revision} exported as CSV; no message was sent.",
        )
        return {
            "filename": f"outreach-{draft.id}.csv",
            "mimeType": "text/csv;charset=utf-8",
            "content": output.getvalue(),
            "draft": _draft_dict(draft),
        }


def export_lead_data(lead_id: str) -> dict[str, str]:
    with write_session() as session:
        lead = session.get(Lead, lead_id)
        if lead is None:
            raise AppError("Lead not found.", 404)
        drafts = list(
            session.scalars(
                select(OutreachDraft)
                .where(OutreachDraft.lead_id == lead.id)
                .order_by(OutreachDraft.created_at.desc())
            ).all()
        )
        content = json.dumps(
            {"lead": _lead_dict(lead), "outreachDrafts": [_draft_dict(item) for item in drafts]},
            ensure_ascii=False,
            indent=2,
        )
        append_audit(
            session,
            action="lead.data_exported",
            entity_type="lead",
            entity_id=lead.id,
            summary="Lead data package exported from the local database.",
        )
        return {
            "filename": f"lead-{lead.id}.json",
            "mimeType": "application/json;charset=utf-8",
            "content": content,
        }


def delete_lead_data(lead_id: str, payload: LeadDeleteRequest) -> dict[str, Any]:
    with write_session() as session:
        lead = session.get(Lead, lead_id)
        if lead is None:
            raise AppError("Lead not found.", 404)
        contact_id = lead.contact_id
        company_id = lead.company_id
        session.delete(lead)
        session.flush()
        if contact_id and session.scalar(select(Lead.id).where(Lead.contact_id == contact_id)) is None:
            contact = session.get(Contact, contact_id)
            if contact is not None:
                session.delete(contact)
                session.flush()
        if company_id:
            has_lead = session.scalar(select(Lead.id).where(Lead.company_id == company_id)) is not None
            has_contact = session.scalar(select(Contact.id).where(Contact.company_id == company_id)) is not None
            if not has_lead and not has_contact:
                company = session.get(Company, company_id)
                if company is not None:
                    session.delete(company)
        append_audit(
            session,
            action="lead.data_deleted",
            entity_type="lead",
            entity_id=lead_id,
            summary="Lead record and outreach drafts permanently deleted after an operator-supplied reason and typed confirmation.",
        )
        return {"deletedId": lead_id}
