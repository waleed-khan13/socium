from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select

from app.database import read_session, write_session
from app.errors import AppError
from app.lead_store import _sync_normalized_records, outreach_state
from app.models import (
    CampaignMember,
    CampaignStep,
    Company,
    Contact,
    Lead,
    LeadCampaign,
    LocalJob,
    OutreachDraft,
)
from app.schemas import CampaignMemberStop, LeadCampaignCreate, LeadCampaignStatusUpdate
from app.store import append_audit, utc_now


def _company_dict(company: Company, contact_count: int) -> dict[str, Any]:
    return {
        "id": company.id,
        "name": company.name,
        "domain": company.domain,
        "website": company.website,
        "location": company.location,
        "source": company.source,
        "sourceRef": company.source_ref,
        "evidence": list(company.evidence or []),
        "contactCount": contact_count,
        "createdAt": company.created_at,
        "updatedAt": company.updated_at,
    }


def _contact_dict(contact: Contact, company: Company | None) -> dict[str, Any]:
    return {
        "id": contact.id,
        "companyId": contact.company_id,
        "companyName": company.name if company else "",
        "fullName": contact.full_name,
        "jobTitle": contact.job_title,
        "email": contact.email,
        "phone": contact.phone,
        "source": contact.source,
        "sourceRef": contact.source_ref,
        "status": contact.status,
        "suppressed": contact.suppressed,
        "suppressionReason": contact.suppression_reason,
        "consentStatus": contact.consent_status,
        "legalBasis": contact.legal_basis,
        "retentionUntil": contact.retention_until,
        "createdAt": contact.created_at,
        "updatedAt": contact.updated_at,
    }


def _step_dict(step: CampaignStep) -> dict[str, Any]:
    return {
        "id": step.id,
        "position": step.position,
        "waitDays": step.wait_days,
        "subjectTemplate": step.subject_template,
        "bodyTemplate": step.body_template,
    }


def _member_dict(member: CampaignMember, lead: Lead | None, contact: Contact | None) -> dict[str, Any]:
    return {
        "id": member.id,
        "leadId": member.lead_id,
        "contactId": member.contact_id,
        "label": (lead.business_name if lead else "") or (contact.email if contact else "") or "Contact",
        "email": contact.email if contact else None,
        "status": member.status,
        "currentStep": member.current_step,
        "stopReason": member.stop_reason,
        "lastDraftId": member.last_draft_id,
        "nextActionAt": member.next_action_at,
        "updatedAt": member.updated_at,
    }


def _campaign_dict(session, campaign: LeadCampaign) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    steps = list(
        session.scalars(
            select(CampaignStep)
            .where(CampaignStep.campaign_id == campaign.id)
            .order_by(CampaignStep.position)
        ).all()
    )
    members = list(
        session.scalars(
            select(CampaignMember)
            .where(CampaignMember.campaign_id == campaign.id)
            .order_by(CampaignMember.created_at)
        ).all()
    )
    lead_ids = [member.lead_id for member in members if member.lead_id]
    contact_ids = [member.contact_id for member in members]
    leads = {
        lead.id: lead
        for lead in session.scalars(select(Lead).where(Lead.id.in_(lead_ids))).all()
    } if lead_ids else {}
    contacts = {
        contact.id: contact
        for contact in session.scalars(select(Contact).where(Contact.id.in_(contact_ids))).all()
    } if contact_ids else {}
    counts = Counter(member.status for member in members)
    return {
        "id": campaign.id,
        "name": campaign.name,
        "objective": campaign.objective,
        "tone": campaign.tone,
        "status": campaign.status,
        "approvalRequired": campaign.approval_required,
        "stopOnReply": campaign.stop_on_reply,
        "stopOnConsentChange": campaign.stop_on_consent_change,
        "steps": [_step_dict(step) for step in steps],
        "members": [_member_dict(member, leads.get(member.lead_id or ""), contacts.get(member.contact_id)) for member in members],
        "memberCounts": dict(counts),
        "createdAt": campaign.created_at,
        "updatedAt": campaign.updated_at,
        "activatedAt": campaign.activated_at,
    }


def growth_state() -> dict[str, Any]:
    with read_session() as session:
        companies = list(session.scalars(select(Company).order_by(Company.updated_at.desc())).all())
        contact_counts = dict(
            session.execute(
                select(Contact.company_id, func.count(Contact.id)).group_by(Contact.company_id)
            ).all()
        )
        contacts = list(session.scalars(select(Contact).order_by(Contact.updated_at.desc())).all())
        company_map = {
            company.id: company
            for company in companies
        }
        campaigns = list(
            session.scalars(select(LeadCampaign).order_by(LeadCampaign.created_at.desc())).all()
        )
        return {
            "companies": [_company_dict(company, int(contact_counts.get(company.id, 0))) for company in companies],
            "contacts": [_contact_dict(contact, company_map.get(contact.company_id or "")) for contact in contacts],
            "campaigns": [_campaign_dict(session, campaign) for campaign in campaigns],
            "summary": {
                "companies": len(companies),
                "contacts": len(contacts),
                "campaigns": len(campaigns),
                "activeCampaigns": sum(campaign.status == "active" for campaign in campaigns),
            },
        }


def create_campaign(payload: LeadCampaignCreate) -> dict[str, Any]:
    with write_session() as session:
        leads = list(session.scalars(select(Lead).where(Lead.id.in_(payload.lead_ids))).all())
        by_id = {lead.id: lead for lead in leads}
        missing = [lead_id for lead_id in payload.lead_ids if lead_id not in by_id]
        if missing:
            raise AppError("One or more selected leads no longer exist.", 404)
        now = utc_now()
        campaign = LeadCampaign(
            id=str(uuid4()),
            workspace_id=1,
            name=payload.name,
            objective=payload.objective,
            tone=payload.tone,
            status="draft",
            approval_required=True,
            stop_on_reply=payload.stop_on_reply,
            stop_on_consent_change=payload.stop_on_consent_change,
            created_at=now,
            updated_at=now,
            activated_at=None,
        )
        session.add(campaign)
        session.flush()
        for position, item in enumerate(payload.steps):
            session.add(
                CampaignStep(
                    id=str(uuid4()),
                    campaign_id=campaign.id,
                    position=position,
                    wait_days=item.wait_days,
                    subject_template=item.subject_template,
                    body_template=item.body_template,
                    created_at=now,
                )
            )
        for lead_id in payload.lead_ids:
            lead = by_id[lead_id]
            _sync_normalized_records(session, lead)
            readiness = outreach_state(lead)
            blockers = readiness["outreachBlockers"]
            blocked = not readiness["outreachReady"]
            session.add(
                CampaignMember(
                    id=str(uuid4()),
                    campaign_id=campaign.id,
                    contact_id=str(lead.contact_id),
                    lead_id=lead.id,
                    status="blocked" if blocked else "pending",
                    current_step=0,
                    stop_reason=str(blockers[0]) if blocked and isinstance(blockers, list) and blockers else None,
                    last_draft_id=None,
                    next_action_at=None,
                    created_at=now,
                    updated_at=now,
                )
            )
        session.flush()
        append_audit(
            session,
            action="campaign.created",
            entity_type="campaign",
            entity_id=campaign.id,
            summary=f"Lead campaign created with {len(leads)} contacts; all delivery remains approval-gated.",
        )
        return _campaign_dict(session, campaign)


def _render(template: str, lead: Lead) -> str:
    values = {
        "business_name": lead.business_name or "your team",
        "email": lead.email or "",
        "website": lead.website or "",
        "location": lead.location or "",
    }
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    return rendered


def advance_campaign_after_export_in_session(session, draft_id: str) -> None:  # type: ignore[no-untyped-def]
    member = session.scalar(select(CampaignMember).where(CampaignMember.last_draft_id == draft_id))
    if member is None or member.status in {"stopped", "completed"}:
        return
    campaign = session.get(LeadCampaign, member.campaign_id)
    if campaign is None or campaign.status != "active":
        return
    next_position = member.current_step + 1
    next_step = session.scalar(
        select(CampaignStep).where(
            CampaignStep.campaign_id == campaign.id,
            CampaignStep.position == next_position,
        )
    )
    now = datetime.now(UTC)
    if next_step is None:
        member.status = "completed"
        member.next_action_at = None
        member.updated_at = utc_now()
        return
    run_at = (now + timedelta(days=next_step.wait_days)).isoformat().replace("+00:00", "Z")
    existing = session.scalar(
        select(LocalJob).where(LocalJob.idempotency_key == f"campaign.prepare:{member.id}:{next_position}")
    )
    if existing is None:
        session.add(
            LocalJob(
                id=str(uuid4()),
                idempotency_key=f"campaign.prepare:{member.id}:{next_position}",
                kind="campaign.prepare",
                status="queued",
                payload={"member_id": member.id, "step": next_position},
                run_at=run_at,
                attempts=0,
                max_attempts=3,
                locked_at=None,
                completed_at=None,
                last_error=None,
                progress_percent=0,
                progress_message="Waiting to prepare the next approval-gated campaign draft.",
                created_at=utc_now(),
                updated_at=utc_now(),
            )
        )
    member.status = "waiting"
    member.next_action_at = run_at
    member.updated_at = utc_now()


def prepare_due_campaign_step(member_id: str) -> str:
    with write_session() as session:
        member = session.get(CampaignMember, member_id)
        if member is None:
            raise AppError("Campaign member no longer exists.", 404)
        campaign = session.get(LeadCampaign, member.campaign_id)
        lead = session.get(Lead, member.lead_id) if member.lead_id else None
        # A queued job can race with pause, reply, suppression, or deletion. Those
        # state changes are intentional terminal/no-op outcomes, not retryable
        # worker failures.
        if member.status != "waiting" or campaign is None or campaign.status != "active":
            return member.id
        if lead is None:
            member.status = "stopped"
            member.stop_reason = "Source lead was deleted."
            member.next_action_at = None
            member.updated_at = utc_now()
            return member.id
        readiness = outreach_state(lead)
        if not readiness["outreachReady"]:
            blockers = readiness["outreachBlockers"]
            member.status = "stopped"
            member.stop_reason = str(blockers[0]) if isinstance(blockers, list) and blockers else "Compliance gate changed."
            member.next_action_at = None
            member.updated_at = utc_now()
            return member.id
        next_position = member.current_step + 1
        step = session.scalar(
            select(CampaignStep).where(
                CampaignStep.campaign_id == campaign.id,
                CampaignStep.position == next_position,
            )
        )
        if step is None:
            member.status = "completed"
            member.next_action_at = None
            member.updated_at = utc_now()
            return member.id
        now = utc_now()
        draft = OutreachDraft(
            id=str(uuid4()),
            lead_id=lead.id,
            revision=1,
            channel="email",
            objective=campaign.objective,
            tone=campaign.tone,
            subject=_render(step.subject_template, lead)[:200],
            body=_render(step.body_template, lead)[:12_000],
            rationale=f"Campaign step {next_position + 1} for {campaign.name}; human approval is required.",
            status="draft",
            provider_kind="campaign-template",
            model="deterministic",
            created_at=now,
            updated_at=now,
            approved_at=None,
            exported_at=None,
        )
        session.add(draft)
        session.flush()
        member.current_step = next_position
        member.last_draft_id = draft.id
        member.status = "awaiting_approval"
        member.next_action_at = None
        member.updated_at = now
        append_audit(
            session,
            action="campaign.follow_up_prepared",
            entity_type="campaign_member",
            entity_id=member.id,
            summary=f"Campaign step {next_position + 1} prepared as a draft; human approval is required.",
        )
        return draft.id


def update_campaign_status(campaign_id: str, payload: LeadCampaignStatusUpdate) -> dict[str, Any]:
    with write_session() as session:
        campaign = session.get(LeadCampaign, campaign_id)
        if campaign is None:
            raise AppError("Campaign not found.", 404)
        if payload.status == "active":
            if campaign.status == "archived":
                raise AppError("Archived campaigns cannot be reactivated.")
            step = session.scalar(
                select(CampaignStep)
                .where(CampaignStep.campaign_id == campaign.id, CampaignStep.position == 0)
            )
            if step is None:
                raise AppError("Campaign needs at least one sequence step.")
            members = list(
                session.scalars(
                    select(CampaignMember).where(
                        CampaignMember.campaign_id == campaign.id,
                        CampaignMember.status.in_(["pending", "blocked", "waiting"]),
                    )
                ).all()
            )
            prepared = 0
            for member in members:
                lead = session.get(Lead, member.lead_id) if member.lead_id else None
                if lead is None:
                    member.status = "stopped"
                    member.stop_reason = "Source lead was deleted."
                    continue
                readiness = outreach_state(lead)
                if not readiness["outreachReady"]:
                    blockers = readiness["outreachBlockers"]
                    member.status = "blocked"
                    member.stop_reason = str(blockers[0]) if isinstance(blockers, list) and blockers else "Compliance review required."
                    continue
                if member.status == "waiting":
                    next_position = member.current_step + 1
                    key = f"campaign.prepare:{member.id}:{next_position}"
                    job = session.scalar(select(LocalJob).where(LocalJob.idempotency_key == key))
                    if job is not None and job.status in {"cancelled", "failed", "completed", "skipped"}:
                        job.status = "queued"
                        job.run_at = member.next_action_at or utc_now()
                        job.attempts = 0
                        job.locked_at = None
                        job.lease_token = None
                        job.lease_expires_at = None
                        job.completed_at = None
                        job.last_error = None
                        job.updated_at = utc_now()
                    prepared += 1
                    continue
                draft = OutreachDraft(
                    id=str(uuid4()),
                    lead_id=lead.id,
                    revision=1,
                    channel="email",
                    objective=campaign.objective,
                    tone=campaign.tone,
                    subject=_render(step.subject_template, lead)[:200],
                    body=_render(step.body_template, lead)[:12_000],
                    rationale=f"Campaign step 1 for {campaign.name}; human approval is required.",
                    status="draft",
                    provider_kind="campaign-template",
                    model="deterministic",
                    created_at=utc_now(),
                    updated_at=utc_now(),
                    approved_at=None,
                    exported_at=None,
                )
                session.add(draft)
                session.flush()
                member.status = "awaiting_approval"
                member.stop_reason = None
                member.last_draft_id = draft.id
                member.current_step = 0
                member.next_action_at = None
                member.updated_at = utc_now()
                prepared += 1
            if prepared == 0 and members:
                raise AppError("No selected contact currently passes the outreach compliance gate.")
            campaign.activated_at = campaign.activated_at or utc_now()
        elif payload.status in {"paused", "archived"}:
            member_ids = list(
                session.scalars(
                    select(CampaignMember.id).where(CampaignMember.campaign_id == campaign.id)
                ).all()
            )
            jobs = list(
                session.scalars(
                    select(LocalJob).where(
                        LocalJob.kind == "campaign.prepare",
                        LocalJob.status.in_(["queued", "retrying"]),
                    )
                ).all()
            )
            now = utc_now()
            for job in jobs:
                if str((job.payload or {}).get("member_id") or "") not in member_ids:
                    continue
                job.status = "cancelled"
                job.completed_at = now
                job.last_error = f"Campaign was {payload.status}."
                job.updated_at = now
        campaign.status = payload.status
        campaign.updated_at = utc_now()
        append_audit(
            session,
            action=f"campaign.{payload.status}",
            entity_type="campaign",
            entity_id=campaign.id,
            summary=(
                "Campaign activated; review-required drafts were prepared and nothing was sent."
                if payload.status == "active"
                else f"Campaign moved to {payload.status}."
            ),
        )
        return _campaign_dict(session, campaign)


def stop_campaign_member(campaign_id: str, member_id: str, payload: CampaignMemberStop) -> dict[str, Any]:
    with write_session() as session:
        campaign = session.get(LeadCampaign, campaign_id)
        member = session.get(CampaignMember, member_id)
        if campaign is None or member is None or member.campaign_id != campaign.id:
            raise AppError("Campaign member not found.", 404)
        member.status = "stopped"
        member.stop_reason = payload.reason
        member.next_action_at = None
        member.updated_at = utc_now()
        append_audit(
            session,
            action="campaign.member_stopped",
            entity_type="campaign_member",
            entity_id=member.id,
            summary=f"Campaign contact stopped: {payload.reason}",
        )
        return _campaign_dict(session, campaign)


def stop_campaign_members_for_reply(sender_email: str, received_at: str | None = None) -> int:
    """Called by inbox sync so a real reply deterministically stops matching sequences."""
    normalized = sender_email.strip().casefold()
    if not normalized:
        return 0
    with write_session() as session:
        return stop_campaign_members_for_reply_in_session(session, normalized, received_at)


def stop_campaign_members_for_reply_in_session(  # type: ignore[no-untyped-def]
    session, sender_email: str, received_at: str | None = None
) -> int:
    normalized = sender_email.strip().casefold()
    if not normalized:
        return 0
    contacts = list(session.scalars(select(Contact).where(func.lower(Contact.email) == normalized)).all())
    if not contacts:
        return 0
    contact_ids = [contact.id for contact in contacts]
    cutoff = received_at or utc_now()
    campaigns = select(LeadCampaign.id).where(
        LeadCampaign.stop_on_reply.is_(True),
        LeadCampaign.activated_at.is_not(None),
        LeadCampaign.activated_at <= cutoff,
    )
    members = list(
        session.scalars(
            select(CampaignMember).where(
                CampaignMember.contact_id.in_(contact_ids),
                CampaignMember.campaign_id.in_(campaigns),
                CampaignMember.status.not_in(["stopped", "completed"]),
            )
        ).all()
    )
    now = utc_now()
    for member in members:
        member.status = "stopped"
        member.stop_reason = "Reply received in Gmail."
        member.next_action_at = None
        member.updated_at = now
    return len(members)
