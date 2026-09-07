from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.utils import parseaddr
from typing import Any
from uuid import uuid4

from sqlalchemy import select

from app.database import read_session, write_session
from app.errors import AppError
from app.growth_store import stop_campaign_members_for_reply_in_session
from app.models import (
    ApprovalRequestRecord,
    EmailMessage,
    EmailReplyDraft,
    EmailThread,
    InboxItem,
    LocalJob,
)
from app.schemas import EmailReplyScheduleRequest, EmailReplyUpdate
from app.store import append_audit, utc_now


def _utc_iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _message_dict(message: EmailMessage) -> dict[str, Any]:
    return {
        "id": message.id,
        "providerMessageId": message.provider_message_id,
        "internetMessageId": message.internet_message_id,
        "direction": message.direction,
        "sender": message.sender,
        "recipients": message.recipients or [],
        "subject": message.subject,
        "bodyText": message.body_text,
        "snippet": message.snippet,
        "references": message.references,
        "sentAt": message.sent_at,
    }


def _draft_dict(draft: EmailReplyDraft | None) -> dict[str, Any] | None:
    if draft is None:
        return None
    return {
        "id": draft.id,
        "threadId": draft.thread_id,
        "approvalRequestId": draft.approval_request_id,
        "revision": draft.revision,
        "subject": draft.subject,
        "body": draft.body,
        "rationale": draft.rationale,
        "classification": draft.classification,
        "status": draft.status,
        "scheduledFor": draft.scheduled_for,
        "providerMessageId": draft.provider_message_id,
        "sentAt": draft.sent_at,
        "lastError": draft.last_error,
        "createdAt": draft.created_at,
        "updatedAt": draft.updated_at,
    }


def _thread_dict(
    thread: EmailThread,
    *,
    messages: list[EmailMessage] | None = None,
    draft: EmailReplyDraft | None = None,
) -> dict[str, Any]:
    return {
        "id": thread.id,
        "workspaceId": thread.workspace_id,
        "connectorAccountId": thread.connector_account_id,
        "providerThreadId": thread.provider_thread_id,
        "subject": thread.subject,
        "snippet": thread.snippet,
        "senderName": thread.sender_name,
        "senderEmail": thread.sender_email,
        "participants": thread.participants or [],
        "classification": thread.classification,
        "priority": thread.priority,
        "status": thread.status,
        "unread": thread.unread,
        "lastMessageAt": thread.last_message_at,
        "createdAt": thread.created_at,
        "updatedAt": thread.updated_at,
        "messages": [_message_dict(item) for item in messages] if messages is not None else None,
        "draft": _draft_dict(draft),
    }


def upsert_gmail_threads(
    account_id: str,
    threads: list[dict[str, Any]],
    *,
    workspace_id: int = 1,
) -> dict[str, int]:
    created = 0
    updated = 0
    now = utc_now()
    with write_session() as session:
        for raw in threads:
            provider_thread_id = str(raw.get("providerThreadId") or "")
            if not provider_thread_id:
                continue
            thread = session.scalar(
                select(EmailThread).where(
                    EmailThread.connector_account_id == account_id,
                    EmailThread.provider_thread_id == provider_thread_id,
                )
            )
            previous_history = thread.history_id if thread is not None else None
            if thread is None:
                thread = EmailThread(
                    id=str(uuid4()),
                    workspace_id=workspace_id,
                    connector_account_id=account_id,
                    provider_thread_id=provider_thread_id,
                    history_id=None,
                    subject="",
                    snippet="",
                    sender_name="",
                    sender_email="",
                    participants=[],
                    classification="needs_review",
                    priority="normal",
                    status="open",
                    unread=False,
                    last_message_at=now,
                    created_at=now,
                    updated_at=now,
                )
                session.add(thread)
                session.flush()
                created += 1
            else:
                updated += 1
            thread.history_id = str(raw.get("historyId") or "") or None
            thread.subject = str(raw.get("subject") or "(No subject)")[:998]
            thread.snippet = str(raw.get("snippet") or "")[:2_000]
            thread.sender_name = str(raw.get("senderName") or "")[:320]
            thread.sender_email = str(raw.get("senderEmail") or "")[:320]
            thread.participants = list(raw.get("participants") or [])[:100]
            thread.classification = str(raw.get("classification") or "needs_review")[:40]
            thread.priority = str(raw.get("priority") or "normal")[:20]
            thread.unread = bool(raw.get("unread"))
            thread.last_message_at = str(raw.get("lastMessageAt") or now)[:40]
            thread.updated_at = now
            if previous_history and previous_history != thread.history_id:
                thread.status = "open"

            if thread.sender_email:
                stop_campaign_members_for_reply_in_session(
                    session, thread.sender_email, thread.last_message_at
                )

            for raw_message in raw.get("messages") or []:
                provider_message_id = str(raw_message.get("providerMessageId") or "")
                if not provider_message_id:
                    continue
                message = session.scalar(
                    select(EmailMessage).where(
                        EmailMessage.thread_id == thread.id,
                        EmailMessage.provider_message_id == provider_message_id,
                    )
                )
                if message is None:
                    message = EmailMessage(
                        id=str(uuid4()),
                        thread_id=thread.id,
                        provider_message_id=provider_message_id[:255],
                        internet_message_id=str(raw_message.get("internetMessageId") or "")[:998],
                        direction=str(raw_message.get("direction") or "inbound")[:20],
                        sender=str(raw_message.get("sender") or "")[:998],
                        recipients=list(raw_message.get("recipients") or [])[:100],
                        subject=str(raw_message.get("subject") or "")[:998],
                        body_text=str(raw_message.get("bodyText") or "")[:100_000],
                        snippet=str(raw_message.get("snippet") or "")[:2_000],
                        references=str(raw_message.get("references") or "")[:8_000],
                        sent_at=str(raw_message.get("sentAt") or now)[:40],
                        created_at=now,
                    )
                    session.add(message)

            inbox = session.scalar(
                select(InboxItem).where(InboxItem.dedupe_key == f"gmail:{account_id}:{provider_thread_id}")
            )
            if inbox is None:
                inbox = InboxItem(
                    id=str(uuid4()),
                    workspace_id=workspace_id,
                    kind="email",
                    priority=thread.priority,
                    status="open",
                    title=thread.subject[:240],
                    body=thread.snippet,
                    entity_type="email_thread",
                    entity_id=thread.id,
                    action_url=f"/?view=inbox&thread={thread.id}",
                    metadata_json={},
                    dedupe_key=f"gmail:{account_id}:{provider_thread_id}",
                    resolved_at=None,
                    created_at=now,
                    updated_at=now,
                )
                session.add(inbox)
            elif not previous_history or previous_history != thread.history_id:
                inbox.status = "open"
                inbox.resolved_at = None
            inbox.priority = thread.priority
            inbox.title = thread.subject[:240]
            inbox.body = thread.snippet
            inbox.metadata_json = {
                "senderName": thread.sender_name,
                "senderEmail": thread.sender_email,
                "classification": thread.classification,
                "unread": thread.unread,
            }
            inbox.updated_at = now

        append_audit(
            session,
            action="gmail.synced",
            entity_type="connector",
            entity_id=account_id,
            summary=f"Gmail sync stored {created} new and refreshed {updated} existing threads locally.",
        )
    return {"created": created, "updated": updated, "total": created + updated}


def list_email_threads(
    workspace_id: int = 1,
    *,
    status: str | None = "open",
    query: str = "",
    limit: int = 100,
) -> list[dict[str, Any]]:
    with read_session() as session:
        statement = select(EmailThread).where(EmailThread.workspace_id == workspace_id)
        if status:
            statement = statement.where(EmailThread.status == status)
        if query.strip():
            pattern = f"%{query.strip()[:200]}%"
            statement = statement.where(
                EmailThread.subject.ilike(pattern)
                | EmailThread.snippet.ilike(pattern)
                | EmailThread.sender_email.ilike(pattern)
                | EmailThread.sender_name.ilike(pattern)
            )
        threads = list(
            session.scalars(
                statement.order_by(EmailThread.last_message_at.desc()).limit(min(max(limit, 1), 500))
            ).all()
        )
        result: list[dict[str, Any]] = []
        for thread in threads:
            draft = session.scalar(
                select(EmailReplyDraft)
                .where(EmailReplyDraft.thread_id == thread.id)
                .order_by(EmailReplyDraft.revision.desc())
                .limit(1)
            )
            result.append(_thread_dict(thread, draft=draft))
        return result


def get_email_thread(thread_id: str, workspace_id: int = 1) -> dict[str, Any]:
    with read_session() as session:
        thread = session.get(EmailThread, thread_id)
        if thread is None or thread.workspace_id != workspace_id:
            raise AppError("Email thread not found.", 404)
        messages = list(
            session.scalars(
                select(EmailMessage)
                .where(EmailMessage.thread_id == thread.id)
                .order_by(EmailMessage.sent_at.asc())
            ).all()
        )
        draft = session.scalar(
            select(EmailReplyDraft)
            .where(EmailReplyDraft.thread_id == thread.id)
            .order_by(EmailReplyDraft.revision.desc())
            .limit(1)
        )
        return _thread_dict(thread, messages=messages, draft=draft)


def schedule_email_reply_generation(thread_id: str, instruction: str) -> dict[str, Any]:
    now = utc_now()
    with write_session() as session:
        thread = session.get(EmailThread, thread_id)
        if thread is None:
            raise AppError("Email thread not found.", 404)
        active = session.scalar(
            select(LocalJob).where(
                LocalJob.kind == "email.reply.generate",
                LocalJob.status.in_({"queued", "retrying", "running"}),
                LocalJob.payload["thread_id"].as_string() == thread_id,
            )
        )
        if active is not None:
            return _job_dict(active)
        job = LocalJob(
            id=str(uuid4()),
            idempotency_key=f"email.reply.generate:{thread_id}:{uuid4()}",
            kind="email.reply.generate",
            status="queued",
            payload={"thread_id": thread_id, "instruction": instruction[:2_000]},
            run_at=now,
            attempts=0,
            max_attempts=3,
            locked_at=None,
            completed_at=None,
            last_error=None,
            progress_percent=0,
            progress_message="Email reply queued for the bounded local worker.",
            created_at=now,
            updated_at=now,
        )
        session.add(job)
        append_audit(
            session,
            action="email.reply_queued",
            entity_type="email_thread",
            entity_id=thread_id,
            summary="AI email reply drafting queued for human approval.",
        )
        session.flush()
        return _job_dict(job)


def _job_dict(job: LocalJob) -> dict[str, Any]:
    return {
        "id": job.id,
        "kind": job.kind,
        "status": job.status,
        "progressPercent": job.progress_percent,
        "progressMessage": job.progress_message,
        "resultRef": job.result_ref,
        "lastError": job.last_error,
        "runAt": job.run_at,
        "recoveryRequiredAt": job.recovery_required_at,
        "recoveryReason": job.recovery_reason,
        "createdAt": job.created_at,
        "updatedAt": job.updated_at,
    }


def get_email_job(job_id: str) -> dict[str, Any]:
    with read_session() as session:
        job = session.get(LocalJob, job_id)
        if job is None or job.kind not in {"email.reply.generate", "email.send"}:
            raise AppError("Email job not found.", 404)
        return _job_dict(job)


def list_email_jobs(*, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    with read_session() as session:
        statement = select(LocalJob).where(LocalJob.kind.in_({"email.reply.generate", "email.send"}))
        if status:
            statement = statement.where(LocalJob.status == status)
        jobs = session.scalars(
            statement.order_by(LocalJob.created_at.desc()).limit(min(max(limit, 1), 100))
        ).all()
        return [_job_dict(job) for job in jobs]


def update_email_job_progress(
    job_id: str,
    percent: int,
    message: str,
    *,
    lease_token: str | None = None,
) -> None:
    with write_session() as session:
        job = session.get(LocalJob, job_id)
        if job is None or job.kind != "email.reply.generate" or job.status != "running":
            return
        if lease_token is not None and job.lease_token != lease_token:
            return
        job.progress_percent = min(max(percent, job.progress_percent), 99)
        job.progress_message = message[:500]
        job.updated_at = utc_now()


def complete_email_reply_generation(
    job_id: str,
    *,
    subject: str,
    body: str,
    rationale: str,
    classification: str,
    lease_token: str | None,
) -> dict[str, Any]:
    now = utc_now()
    with write_session() as session:
        job = session.get(LocalJob, job_id)
        if job is None or job.kind != "email.reply.generate" or job.status != "running":
            raise AppError("Email reply job is no longer active.", 409)
        if lease_token is not None and job.lease_token != lease_token:
            raise AppError("Email reply job lease expired.", 409)
        thread_id = str((job.payload or {}).get("thread_id") or "")
        thread = session.get(EmailThread, thread_id)
        if thread is None:
            raise AppError("Email thread was removed before drafting completed.", 404)
        previous = list(
            session.scalars(
                select(EmailReplyDraft)
                .where(EmailReplyDraft.thread_id == thread_id)
                .order_by(EmailReplyDraft.revision.desc())
            ).all()
        )
        scheduled_jobs = list(
            session.scalars(
                select(LocalJob).where(
                    LocalJob.kind == "email.send",
                    LocalJob.status.in_({"queued", "retrying", "missed"}),
                )
            ).all()
        )
        revision = (previous[0].revision + 1) if previous else 1
        for item in previous:
            if item.status in {"pending", "approved", "scheduled", "failed"}:
                item.status = "superseded"
                item.updated_at = now
                if item.approval_request_id:
                    approval = session.get(ApprovalRequestRecord, item.approval_request_id)
                    if approval is not None and approval.status == "pending":
                        approval.status = "regenerate_text"
                        approval.decided_action = "regenerate_text"
                        approval.decided_by = "Socium regeneration"
                        approval.decision_source = "dashboard"
                        approval.decided_at = now
                        approval.updated_at = now
            for scheduled_job in scheduled_jobs:
                if str((scheduled_job.payload or {}).get("draft_id") or "") != item.id:
                    continue
                scheduled_job.status = "cancelled"
                scheduled_job.completed_at = now
                scheduled_job.recovery_required_at = None
                scheduled_job.recovery_reason = None
                scheduled_job.last_error = "A newer reply revision replaced this scheduled email."
                scheduled_job.updated_at = now
        draft = EmailReplyDraft(
            id=str(uuid4()),
            thread_id=thread_id,
            approval_request_id=None,
            revision=revision,
            subject=subject[:998],
            body=body[:50_000],
            rationale=rationale[:1_000],
            classification=classification[:40],
            status="pending",
            scheduled_for=None,
            provider_message_id=None,
            sent_at=None,
            last_error=None,
            created_at=now,
            updated_at=now,
        )
        session.add(draft)
        session.flush()
        approval = ApprovalRequestRecord(
            id=str(uuid4()),
            workspace_id=thread.workspace_id,
            subject_type="email_reply",
            subject_id=draft.id,
            subject_revision=revision,
            status="pending",
            allowed_actions=["approve", "edit", "regenerate_text", "reject", "skip"],
            expires_at=_utc_iso(datetime.now(UTC) + timedelta(days=7)),
            created_at=now,
            updated_at=now,
        )
        session.add(approval)
        draft.approval_request_id = approval.id
        thread.classification = classification[:40]
        thread.updated_at = now
        inbox = InboxItem(
            id=str(uuid4()),
            workspace_id=thread.workspace_id,
            kind="email_reply_approval",
            priority=thread.priority,
            status="open",
            title=f"Approve reply · {thread.subject}"[:240],
            body=body[:2_000],
            entity_type="email_reply",
            entity_id=draft.id,
            action_url=f"/?view=inbox&thread={thread.id}",
            metadata_json={"threadId": thread.id, "revision": revision},
            dedupe_key=f"approval:{approval.id}",
            resolved_at=None,
            created_at=now,
            updated_at=now,
        )
        session.add(inbox)
        job.status = "completed"
        job.progress_percent = 100
        job.progress_message = "Reply draft ready for human approval."
        job.result_ref = draft.id
        job.completed_at = now
        job.locked_at = None
        job.lease_token = None
        job.lease_expires_at = None
        job.last_error = None
        job.updated_at = now
        append_audit(
            session,
            action="email.reply_drafted",
            entity_type="email_reply",
            entity_id=draft.id,
            summary=f"Email reply revision {revision} created for human approval.",
        )
        session.flush()
        return _draft_dict(draft) or {}


def revise_email_reply(draft_id: str, payload: EmailReplyUpdate) -> dict[str, Any]:
    with read_session() as session:
        current = session.get(EmailReplyDraft, draft_id)
        if current is None:
            raise AppError("Email reply draft not found.", 404)
        thread_id = current.thread_id
    temporary_job_id = str(uuid4())
    now = utc_now()
    with write_session() as session:
        job = LocalJob(
            id=temporary_job_id,
            idempotency_key=f"email.reply.edit:{draft_id}:{uuid4()}",
            kind="email.reply.generate",
            status="running",
            payload={"thread_id": thread_id, "instruction": "Manual edit"},
            run_at=now,
            attempts=1,
            max_attempts=1,
            locked_at=now,
            lease_token=temporary_job_id,
            lease_expires_at=_utc_iso(datetime.now(UTC) + timedelta(minutes=1)),
            completed_at=None,
            last_error=None,
            created_at=now,
            updated_at=now,
        )
        session.add(job)
    return complete_email_reply_generation(
        temporary_job_id,
        subject=payload.subject,
        body=payload.body,
        rationale="Edited by the local operator.",
        classification="needs_reply",
        lease_token=temporary_job_id,
    )


def prepare_email_reply_send(draft_id: str) -> dict[str, Any]:
    now = utc_now()
    with write_session() as session:
        draft = session.get(EmailReplyDraft, draft_id)
        if draft is None:
            raise AppError("Email reply draft not found.", 404)
        if draft.status == "sent":
            raise AppError("This exact email reply was already sent; duplicate send blocked.", 409)
        if draft.status not in {"approved", "scheduled"}:
            raise AppError("Approve this exact email reply revision before sending.")
        thread = session.get(EmailThread, draft.thread_id)
        if thread is None:
            raise AppError("Email thread not found.", 404)
        messages = list(
            session.scalars(
                select(EmailMessage)
                .where(EmailMessage.thread_id == thread.id)
                .order_by(EmailMessage.sent_at.desc())
            ).all()
        )
        inbound = next((item for item in messages if item.direction == "inbound"), None)
        if inbound is None:
            raise AppError("This thread has no inbound sender to reply to.")
        to_address = parseaddr(inbound.sender)[1]
        if not to_address or "@" not in to_address:
            raise AppError("The inbound sender address is invalid.")
        draft.status = "sending"
        draft.last_error = None
        draft.updated_at = now
        append_audit(
            session,
            action="email.send_started",
            entity_type="email_reply",
            entity_id=draft.id,
            summary=f"Approved email reply revision {draft.revision} reserved for one send.",
        )
        return {
            "draftId": draft.id,
            "threadId": thread.id,
            "connectorAccountId": thread.connector_account_id,
            "providerThreadId": thread.provider_thread_id,
            "toAddress": to_address,
            "subject": draft.subject,
            "body": draft.body,
            "internetMessageId": inbound.internet_message_id,
            "references": inbound.references,
            "messageId": f"<socium.{draft.id}.{draft.revision}@socium.local>",
        }


def finish_email_reply_send(draft_id: str, provider_message_id: str) -> dict[str, Any]:
    now = utc_now()
    with write_session() as session:
        draft = session.get(EmailReplyDraft, draft_id)
        if draft is None or draft.status != "sending":
            raise AppError("Email reply send reservation is no longer active.", 409)
        draft.status = "sent"
        draft.provider_message_id = provider_message_id[:255]
        draft.sent_at = now
        draft.scheduled_for = None
        draft.updated_at = now
        pending_send_jobs = session.scalars(
            select(LocalJob).where(
                LocalJob.kind == "email.send",
                LocalJob.status.in_({"queued", "retrying", "missed"}),
            )
        ).all()
        for job in pending_send_jobs:
            if str((job.payload or {}).get("draft_id") or "") != draft.id:
                continue
            job.status = "cancelled"
            job.completed_at = now
            job.recovery_required_at = None
            job.recovery_reason = None
            job.last_error = "The approved reply was sent manually before this schedule ran."
            job.updated_at = now
        thread = session.get(EmailThread, draft.thread_id)
        if thread is not None:
            thread.status = "resolved"
            thread.unread = False
            thread.classification = "waiting"
            thread.updated_at = now
            original = session.scalar(
                select(InboxItem).where(
                    InboxItem.dedupe_key == f"gmail:{thread.connector_account_id}:{thread.provider_thread_id}"
                )
            )
            if original is not None:
                original.status = "resolved"
                original.resolved_at = now
                original.updated_at = now
        if draft.approval_request_id:
            approval_inbox = session.scalar(
                select(InboxItem).where(InboxItem.dedupe_key == f"approval:{draft.approval_request_id}")
            )
            if approval_inbox is not None:
                approval_inbox.status = "resolved"
                approval_inbox.resolved_at = now
                approval_inbox.updated_at = now
        append_audit(
            session,
            action="email.sent",
            entity_type="email_reply",
            entity_id=draft.id,
            summary=f"Approved email reply revision {draft.revision} sent through Gmail.",
        )
        return _draft_dict(draft) or {}


def fail_email_reply_send(draft_id: str, message: str) -> None:
    with write_session() as session:
        draft = session.get(EmailReplyDraft, draft_id)
        if draft is None or draft.status == "sent":
            return
        draft.status = "failed_uncertain"
        draft.last_error = message[:2_000]
        draft.updated_at = utc_now()
        append_audit(
            session,
            action="email.send_uncertain",
            entity_type="email_reply",
            entity_id=draft.id,
            summary="Gmail delivery could not be confirmed; automatic retry was blocked.",
        )


def schedule_email_reply(draft_id: str, payload: EmailReplyScheduleRequest) -> tuple[dict[str, Any], bool]:
    now_dt = datetime.now(UTC)
    if payload.run_at <= now_dt:
        raise AppError("Choose a future email send time.")
    if payload.run_at > now_dt + timedelta(days=366):
        raise AppError("Scheduled email must be within the next year.")
    with write_session() as session:
        draft = session.get(EmailReplyDraft, draft_id)
        if draft is None:
            raise AppError("Email reply draft not found.", 404)
        if draft.status != "approved":
            raise AppError("Approve this exact email reply revision before scheduling.")
        key = f"email.send:{draft.id}:{draft.revision}"
        existing = session.scalar(select(LocalJob).where(LocalJob.idempotency_key == key))
        if existing is not None:
            return _job_dict(existing), False
        now = utc_now()
        job = LocalJob(
            id=str(uuid4()),
            idempotency_key=key,
            kind="email.send",
            status="queued",
            payload={"draft_id": draft.id, "revision": draft.revision},
            run_at=_utc_iso(payload.run_at),
            attempts=0,
            max_attempts=1,
            locked_at=None,
            completed_at=None,
            last_error=None,
            created_at=now,
            updated_at=now,
        )
        session.add(job)
        draft.status = "scheduled"
        draft.scheduled_for = job.run_at
        draft.updated_at = now
        append_audit(
            session,
            action="email.scheduled",
            entity_type="email_reply",
            entity_id=draft.id,
            summary=f"Approved email reply scheduled for {job.run_at}.",
        )
        session.flush()
        return _job_dict(job), True
