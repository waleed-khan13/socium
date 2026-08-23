from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

from sqlalchemy import select

from app.database import read_session, write_session
from app.errors import AppError
from app.models import LocalJob, SeoAuditSnapshot
from app.schemas import SeoAuditScheduleRequest
from app.services.crawler import normalize_website_url
from app.store import append_audit, utc_now


def _utc_iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _previous_score(session, snapshot: SeoAuditSnapshot) -> int | None:  # type: ignore[no-untyped-def]
    return session.scalar(
        select(SeoAuditSnapshot.overall_score)
        .where(
            SeoAuditSnapshot.hostname == snapshot.hostname,
            SeoAuditSnapshot.created_at < snapshot.created_at,
        )
        .order_by(SeoAuditSnapshot.created_at.desc())
        .limit(1)
    )


def _snapshot_dict(snapshot: SeoAuditSnapshot, previous_score: int | None = None) -> dict[str, Any]:
    return {
        "id": snapshot.id,
        "requestedUrl": snapshot.requested_url,
        "finalUrl": snapshot.final_url,
        "hostname": snapshot.hostname,
        "trigger": snapshot.trigger,
        "statusCode": snapshot.status_code,
        "overallScore": snapshot.overall_score,
        "previousScore": previous_score,
        "scoreDelta": snapshot.overall_score - previous_score if previous_score is not None else None,
        "scores": dict(snapshot.scores or {}),
        "metrics": dict(snapshot.metrics or {}),
        "checks": list(snapshot.checks or []),
        "robotsRespected": snapshot.robots_respected,
        "userAgent": snapshot.user_agent,
        "durationMs": snapshot.duration_ms,
        "createdAt": snapshot.created_at,
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
        "createdAt": job.created_at,
        "updatedAt": job.updated_at,
    }


def save_seo_audit(result: dict[str, Any], *, trigger: str) -> dict[str, Any]:
    now = utc_now()
    with write_session() as session:
        previous = session.scalar(
            select(SeoAuditSnapshot.overall_score)
            .where(SeoAuditSnapshot.hostname == str(result["hostname"]))
            .order_by(SeoAuditSnapshot.created_at.desc())
            .limit(1)
        )
        snapshot = SeoAuditSnapshot(
            id=str(uuid4()),
            requested_url=str(result["requestedUrl"]),
            final_url=str(result["finalUrl"]),
            hostname=str(result["hostname"]),
            trigger=trigger,
            status_code=int(result["statusCode"]),
            overall_score=int(result["overallScore"]),
            scores=dict(result["scores"]),
            metrics=dict(result["metrics"]),
            checks=list(result["checks"]),
            robots_respected=bool(result["robotsRespected"]),
            user_agent=str(result["userAgent"]),
            duration_ms=int(result["durationMs"]),
            created_at=now,
        )
        session.add(snapshot)
        append_audit(
            session,
            action="seo.audit_completed",
            entity_type="seo",
            entity_id=snapshot.id,
            summary=(
                f"Local SEO audit completed for {snapshot.hostname} with score "
                f"{snapshot.overall_score}/100 ({trigger})."
            ),
        )
        session.flush()
        return _snapshot_dict(snapshot, previous)


def list_seo_audits(limit: int = 50) -> dict[str, Any]:
    with read_session() as session:
        all_snapshots = list(
            session.scalars(select(SeoAuditSnapshot).order_by(SeoAuditSnapshot.created_at.desc())).all()
        )
        snapshots = all_snapshots[:limit]
        items = [_snapshot_dict(snapshot, _previous_score(session, snapshot)) for snapshot in snapshots]
        latest_by_host: dict[str, SeoAuditSnapshot] = {}
        for snapshot in all_snapshots:
            latest_by_host.setdefault(snapshot.hostname, snapshot)
        latest = list(latest_by_host.values())
        average = round(sum(item.overall_score for item in latest) / len(latest)) if latest else 0
        failed = sum(1 for snapshot in latest for check in snapshot.checks if check.get("status") == "failed")
        return {
            "items": items,
            "summary": {
                "snapshots": len(all_snapshots),
                "sites": len(latest),
                "averageScore": average,
                "openFailures": failed,
                "lastAuditAt": snapshots[0].created_at if snapshots else None,
            },
        }


def get_seo_audit(snapshot_id: str) -> dict[str, Any]:
    with read_session() as session:
        snapshot = session.get(SeoAuditSnapshot, snapshot_id)
        if snapshot is None:
            raise AppError("SEO audit snapshot not found.", 404)
        return _snapshot_dict(snapshot, _previous_score(session, snapshot))


def schedule_seo_audit(
    payload: SeoAuditScheduleRequest,
    catch_up_hours: int,
) -> tuple[dict[str, Any], bool]:
    now = datetime.now(UTC)
    if payload.run_at < now - timedelta(hours=catch_up_hours):
        raise AppError(f"Scheduled time is outside the {catch_up_hours}-hour catch-up window.")
    if payload.run_at > now + timedelta(days=366):
        raise AppError("Scheduled time must be within the next year.")
    url = normalize_website_url(payload.url)
    run_at = _utc_iso(payload.run_at)
    digest = sha256(f"{url}|{run_at}".encode()).hexdigest()[:40]
    key = f"seo.audit:{digest}"
    with write_session() as session:
        existing = session.scalar(select(LocalJob).where(LocalJob.idempotency_key == key))
        if existing is not None:
            return _job_dict(existing), False
        created_at = utc_now()
        job = LocalJob(
            id=str(uuid4()),
            idempotency_key=key,
            kind="seo.audit",
            status="queued",
            payload={"url": url},
            run_at=run_at,
            attempts=0,
            max_attempts=3,
            locked_at=None,
            completed_at=None,
            last_error=None,
            created_at=created_at,
            updated_at=created_at,
        )
        session.add(job)
        append_audit(
            session,
            action="seo.audit_scheduled",
            entity_type="seo",
            entity_id=job.id,
            summary=f"Local SEO snapshot scheduled for {urlsplit_hostname(url)} at {run_at}.",
        )
        session.flush()
        return _job_dict(job), True


def urlsplit_hostname(url: str) -> str:
    return urlsplit(url).hostname or url


def list_seo_jobs(limit: int = 50) -> dict[str, Any]:
    with read_session() as session:
        jobs = list(
            session.scalars(
                select(LocalJob)
                .where(LocalJob.kind == "seo.audit")
                .order_by(LocalJob.created_at.desc())
                .limit(limit)
            ).all()
        )
        return {"items": [_job_dict(job) for job in jobs]}


def cancel_seo_job(job_id: str) -> dict[str, Any]:
    with write_session() as session:
        job = session.get(LocalJob, job_id)
        if job is None or job.kind != "seo.audit":
            raise AppError("Scheduled SEO audit not found.", 404)
        if job.status not in {"queued", "retrying"}:
            raise AppError(f"Only queued SEO audits can be cancelled. Current status: {job.status}.")
        now = utc_now()
        job.status = "cancelled"
        job.completed_at = now
        job.updated_at = now
        job.last_error = "Cancelled by the local operator."
        append_audit(
            session,
            action="seo.audit_cancelled",
            entity_type="seo",
            entity_id=job.id,
            summary="Scheduled local SEO audit cancelled by the operator.",
        )
        return _job_dict(job)


def retry_seo_job(job_id: str) -> dict[str, Any]:
    with write_session() as session:
        job = session.get(LocalJob, job_id)
        if job is None or job.kind != "seo.audit":
            raise AppError("Scheduled SEO audit not found.", 404)
        if job.status not in {"failed", "missed"}:
            raise AppError(f"Only failed or missed SEO audits can be retried. Current status: {job.status}.")
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
        append_audit(
            session,
            action="seo.audit_retried",
            entity_type="seo",
            entity_id=job.id,
            summary="Scheduled local SEO audit queued again after operator review.",
        )
        return _job_dict(job)
