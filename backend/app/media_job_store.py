from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy import select

from app.database import read_session, write_session
from app.errors import AppError
from app.models import ImageProviderSettings, LocalJob
from app.schemas import ImageGenerateRequest
from app.store import append_audit, utc_now


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


def schedule_media_generation(
    request: ImageGenerateRequest,
    provider: dict[str, str],
) -> dict[str, Any]:
    if not provider.get("updated_at"):
        raise AppError("Save an image provider before queueing generation.")
    now = utc_now()
    job = LocalJob(
        id=str(uuid4()),
        idempotency_key=None,
        kind="media.generate",
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
        locked_at=None,
        completed_at=None,
        last_error=None,
        progress_percent=0,
        progress_message="Waiting for the local image worker.",
        cancel_requested=False,
        remote_ref=None,
        result_ref=None,
        created_at=now,
        updated_at=now,
    )
    with write_session() as session:
        session.add(job)
        append_audit(
            session,
            action="media.generation_queued",
            entity_type="media",
            entity_id=job.id,
            summary=f"Queued private image generation with {provider['kind']}.",
        )
        session.flush()
        return _job_dict(job)


def list_media_generation_jobs(limit: int = 30) -> dict[str, Any]:
    with read_session() as session:
        jobs = list(
            session.scalars(
                select(LocalJob)
                .where(LocalJob.kind == "media.generate")
                .order_by(LocalJob.created_at.desc())
                .limit(limit)
            ).all()
        )
        return {"items": [_job_dict(job) for job in jobs]}


def media_generation_cancel_requested(job_id: str) -> bool:
    with read_session() as session:
        job = session.get(LocalJob, job_id)
        return job is None or job.cancel_requested or job.status == "cancelled"


def update_media_generation_progress(
    job_id: str,
    percent: int,
    message: str,
    *,
    remote_ref: str | None = None,
    lease_token: str | None = None,
) -> None:
    with write_session() as session:
        job = session.get(LocalJob, job_id)
        if (
            job is None
            or job.status != "running"
            or (lease_token is not None and job.lease_token != lease_token)
        ):
            return
        job.progress_percent = max(job.progress_percent, min(max(percent, 0), 99))
        job.progress_message = message[:500]
        if remote_ref:
            job.remote_ref = remote_ref[:255]
        job.updated_at = utc_now()


def complete_media_generation_job(
    job_id: str,
    asset_id: str,
    deduplicated: bool,
    lease_token: str | None = None,
) -> bool:
    with write_session() as session:
        job = session.get(LocalJob, job_id)
        if (
            job is None
            or job.status != "running"
            or (lease_token is not None and job.lease_token != lease_token)
        ):
            return False
        now = utc_now()
        job.status = "completed"
        job.progress_percent = 100
        job.progress_message = "Image saved privately and ready for review."
        job.result_ref = asset_id
        job.locked_at = None
        job.lease_token = None
        job.lease_expires_at = None
        job.completed_at = now
        job.updated_at = now
        append_audit(
            session,
            action="media.generation_completed",
            entity_type="media",
            entity_id=job.id,
            summary=(
                "Generated image matched an existing asset and was reused."
                if deduplicated
                else "Queued image generation completed and was saved privately."
            ),
        )
        return True


def finish_cancelled_media_generation(job_id: str, lease_token: str | None = None) -> bool:
    with write_session() as session:
        job = session.get(LocalJob, job_id)
        if job is None or (lease_token is not None and job.lease_token != lease_token):
            return False
        now = utc_now()
        job.status = "cancelled"
        job.progress_message = "Generation cancelled by the local operator."
        job.last_error = None
        job.locked_at = None
        job.lease_token = None
        job.lease_expires_at = None
        job.completed_at = now
        job.updated_at = now
        append_audit(
            session,
            action="media.generation_cancelled",
            entity_type="media",
            entity_id=job.id,
            summary="Private image generation cancelled by the local operator.",
        )
        return True


def cancel_media_generation(job_id: str) -> dict[str, Any]:
    with write_session() as session:
        job = session.get(LocalJob, job_id)
        if job is None or job.kind != "media.generate":
            raise AppError("Image generation job not found.", 404)
        if job.status in {"queued", "retrying"}:
            now = utc_now()
            job.status = "cancelled"
            job.completed_at = now
            job.progress_message = "Generation cancelled before it started."
            job.updated_at = now
        elif job.status == "running":
            job.cancel_requested = True
            job.progress_message = "Cancellation requested; stopping provider work."
            job.updated_at = utc_now()
        else:
            raise AppError(f"This generation cannot be cancelled. Current status: {job.status}.")
        append_audit(
            session,
            action="media.generation_cancel_requested",
            entity_type="media",
            entity_id=job.id,
            summary="Operator requested cancellation of a private image generation.",
        )
        session.flush()
        return _job_dict(job)


def retry_media_generation(job_id: str) -> dict[str, Any]:
    with write_session() as session:
        job = session.get(LocalJob, job_id)
        if job is None or job.kind != "media.generate":
            raise AppError("Image generation job not found.", 404)
        if job.status not in {"failed", "cancelled", "missed"}:
            raise AppError(f"This generation cannot be retried. Current status: {job.status}.")
        provider = session.get(ImageProviderSettings, 1)
        if provider is None or not provider.updated_at:
            raise AppError("Save an image provider before retrying this generation.")
        now = utc_now()
        payload = dict(job.payload or {})
        payload["provider"] = {
            "kind": provider.kind,
            "model": provider.model,
            "updated_at": provider.updated_at,
        }
        job.payload = payload
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
        job.progress_percent = 0
        job.progress_message = "Waiting for the local image worker."
        job.cancel_requested = False
        job.remote_ref = None
        job.result_ref = None
        job.updated_at = now
        append_audit(
            session,
            action="media.generation_retried",
            entity_type="media",
            entity_id=job.id,
            summary="Image generation queued again after operator review.",
        )
        session.flush()
        return _job_dict(job)
