from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy import select

from app.database import read_session, write_session
from app.errors import AppError
from app.models import LocalJob
from app.schemas import GeneratePostRequest
from app.store import append_audit, utc_now


def _job_dict(job: LocalJob) -> dict[str, Any]:
    payload = dict(job.payload or {})
    return {
        "id": job.id,
        "kind": job.kind,
        "status": job.status,
        "runAt": job.run_at,
        "attempts": job.attempts,
        "maxAttempts": job.max_attempts,
        "completedAt": job.completed_at,
        "lastError": job.last_error,
        "progressPercent": job.progress_percent,
        "progressMessage": job.progress_message,
        "cancelRequested": job.cancel_requested,
        "resultRef": job.result_ref,
        "notifications": payload.get("notifications") or [],
        "createdAt": job.created_at,
        "updatedAt": job.updated_at,
    }


def schedule_content_generation(request: GeneratePostRequest, provider: dict[str, str]) -> dict[str, Any]:
    if not provider.get("updated_at"):
        raise AppError("Save and verify an AI provider before generating content.")
    now = utc_now()
    job = LocalJob(
        id=str(uuid4()),
        idempotency_key=None,
        kind="content.generate",
        status="queued",
        payload={
            "request": request.model_dump(mode="json"),
            "provider": {
                "kind": provider["kind"],
                "model": provider["model"],
                "updated_at": provider["updated_at"],
            },
        },
        run_at=now,
        attempts=0,
        max_attempts=2,
        progress_percent=0,
        progress_message="Queued for the bounded local content worker.",
        cancel_requested=False,
        created_at=now,
        updated_at=now,
    )
    with write_session() as session:
        session.add(job)
        append_audit(
            session,
            action="content.generation_queued",
            entity_type="post",
            entity_id=job.id,
            summary="Queued a content kit for private generation.",
        )
        session.flush()
        return _job_dict(job)


def get_content_generation(job_id: str) -> dict[str, Any]:
    with read_session() as session:
        job = session.get(LocalJob, job_id)
        if job is None or job.kind != "content.generate":
            raise AppError("Content generation job not found.", 404)
        return _job_dict(job)


def list_content_generations(limit: int = 30) -> list[dict[str, Any]]:
    with read_session() as session:
        jobs = session.scalars(
            select(LocalJob)
            .where(LocalJob.kind == "content.generate")
            .order_by(LocalJob.created_at.desc())
            .limit(limit)
        ).all()
        return [_job_dict(job) for job in jobs]


def content_generation_cancel_requested(job_id: str) -> bool:
    with read_session() as session:
        job = session.get(LocalJob, job_id)
        return job is None or job.cancel_requested or job.status == "cancelled"


def update_content_generation_progress(
    job_id: str,
    percent: int,
    message: str,
    *,
    lease_token: str | None = None,
) -> None:
    with write_session() as session:
        job = session.get(LocalJob, job_id)
        if job is None or job.status != "running" or (
            lease_token is not None and job.lease_token != lease_token
        ):
            return
        job.progress_percent = max(job.progress_percent, min(max(percent, 0), 99))
        job.progress_message = message[:500]
        job.updated_at = utc_now()


def complete_content_generation(
    job_id: str,
    post_id: str,
    notifications: list[dict[str, Any]],
    lease_token: str | None,
) -> bool:
    with write_session() as session:
        job = session.get(LocalJob, job_id)
        if job is None or job.status != "running" or (
            lease_token is not None and job.lease_token != lease_token
        ):
            return False
        now = utc_now()
        payload = dict(job.payload or {})
        payload["notifications"] = notifications
        job.payload = payload
        job.status = "completed"
        job.progress_percent = 100
        job.progress_message = "Content kit saved and ready for review."
        job.result_ref = post_id
        job.locked_at = None
        job.lease_token = None
        job.lease_expires_at = None
        job.completed_at = now
        job.updated_at = now
        job.last_error = None
        append_audit(
            session,
            action="content.generation_completed",
            entity_type="post",
            entity_id=post_id,
            summary="Background content generation completed and saved a reviewable draft.",
        )
        return True


def cancel_content_generation(job_id: str) -> dict[str, Any]:
    with write_session() as session:
        job = session.get(LocalJob, job_id)
        if job is None or job.kind != "content.generate":
            raise AppError("Content generation job not found.", 404)
        if job.status in {"queued", "retrying"}:
            now = utc_now()
            job.status = "cancelled"
            job.completed_at = now
            job.progress_message = "Generation cancelled before it started."
            job.updated_at = now
        elif job.status == "running":
            raise AppError("This provider call is already running and will stop at its bounded timeout.")
        else:
            raise AppError(f"This generation cannot be cancelled. Current status: {job.status}.")
        session.flush()
        return _job_dict(job)
