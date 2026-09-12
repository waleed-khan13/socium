from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select

from app.database import read_session, write_session
from app.models import BrowserPublishAttempt, LocalJob, Post, SocialBrowserAccount
from app.social_automation.contracts import AccountCreate, Authentication, AuthState, BrowserError
from app.store import append_audit, utc_now


def account_dict(account: SocialBrowserAccount) -> dict[str, Any]:
    return {
        "id": account.id,
        "platform": account.platform,
        "name": account.name,
        "identity": account.identity,
        "status": account.status,
        "preferred": account.preferred,
        "lastErrorCode": account.last_error_code,
        "lastVerifiedAt": account.last_verified_at,
    }


def account_by_id(account_id: str) -> dict[str, Any]:
    try:
        if str(UUID(account_id)) != account_id:
            raise ValueError
    except ValueError as error:
        raise BrowserError("ACCOUNT_NOT_FOUND", "Browser account not found.") from error
    with read_session() as session:
        account = session.get(SocialBrowserAccount, account_id)
        if account is None:
            raise BrowserError("ACCOUNT_NOT_FOUND", "Browser account not found.")
        return account_dict(account)


def create_account(payload: AccountCreate) -> dict[str, Any]:
    if not payload.acknowledge_policy_risk:
        raise BrowserError("CONSENT_REQUIRED", "Review the platform automation risk before connecting.")
    if not payload.name.strip():
        raise BrowserError("INVALID_NAME", "Give this local account a name.")
    with write_session() as session:
        account = SocialBrowserAccount(
            id=str(uuid4()),
            platform=payload.platform,
            name=payload.name.strip(),
            status="not_connected",
            preferred=False,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        session.add(account)
        session.flush()
        append_audit(
            session,
            action="social.account_created",
            entity_type="social_account",
            entity_id=account.id,
            summary="Local browser account created after risk acknowledgement.",
        )
        return account_dict(account)


def set_preferred(account_id: str) -> None:
    with write_session() as session:
        account = session.get(SocialBrowserAccount, account_id)
        if account is None or account.status != "connected" or not account.identity:
            raise BrowserError("AUTH_REQUIRED", "Connect and verify this browser account first.")
        for item in session.scalars(
            select(SocialBrowserAccount).where(
                SocialBrowserAccount.platform == account.platform,
            )
        ):
            item.preferred = item.id == account.id
        append_audit(
            session,
            action="social.destination_selected",
            entity_type="social_account",
            entity_id=account.id,
            summary="Browser account selected for future drafts only.",
        )


def record_auth(account_id: str, auth: Authentication, code: str | None = None) -> None:
    with write_session() as session:
        account = session.get(SocialBrowserAccount, account_id)
        if account is None:
            raise BrowserError("ACCOUNT_NOT_FOUND", "Browser account not found.")
        # A profile must not silently turn into another person's publishing account.
        if auth.identity and account.identity and account.identity != auth.identity:
            account.status = "requires_verification"
            account.last_error_code = "ACCOUNT_CHANGED"
        else:
            account.status = str(auth.state)
            account.last_error_code = code
            if auth.state == AuthState.AUTHENTICATED and auth.identity:
                account.identity = auth.identity
                account.last_verified_at = utc_now()
        account.updated_at = utc_now()


def queue_operation(kind: str, account_id: str | None = None) -> dict[str, Any]:
    if kind not in {"social.connect", "social.verify", "social.browser.install"}:
        raise BrowserError("INVALID_OPERATION", "Unsupported browser operation.")
    with write_session() as session:
        if account_id and session.get(SocialBrowserAccount, account_id) is None:
            raise BrowserError("ACCOUNT_NOT_FOUND", "Browser account not found.")
        for job in session.scalars(
            select(LocalJob).where(
                LocalJob.kind.like("social.%"),
                LocalJob.status.in_(["queued", "retrying", "running"]),
            )
        ):
            if job.kind == kind and job.payload.get("account_id") == account_id:
                return {"id": job.id, "status": job.status}
        now = utc_now()
        job = LocalJob(
            id=str(uuid4()),
            kind=kind,
            status="queued",
            payload={"account_id": account_id},
            run_at=now,
            attempts=0,
            max_attempts=1,
            created_at=now,
            updated_at=now,
        )
        session.add(job)
        session.flush()
        return {"id": job.id, "status": job.status}


def update_progress(job_id: str, step: str, percent: int) -> None:
    with write_session() as session:
        job = session.get(LocalJob, job_id)
        if job is None or job.cancel_requested or job.status != "running":
            raise BrowserError("CANCELLED", "Browser operation cancelled.")
        job.progress_message = step
        job.progress_percent = percent


def cancel_operation(job_id: str) -> None:
    with write_session() as session:
        job = session.get(LocalJob, job_id)
        if job is None or not job.kind.startswith("social."):
            raise BrowserError("JOB_NOT_FOUND", "Browser setup job not found.")
        job.cancel_requested = True
        if job.status in {"queued", "retrying"}:
            job.status = "cancelled"
            job.completed_at = utc_now()


def public_state() -> dict[str, Any]:
    with read_session() as session:
        accounts = [
            account_dict(a)
            for a in session.scalars(select(SocialBrowserAccount).order_by(SocialBrowserAccount.created_at))
        ]
        jobs = [
            {
                "id": j.id,
                "kind": j.kind,
                "status": j.status,
                "message": j.progress_message,
                "error": j.last_error,
                "progress": j.progress_percent,
                "accountId": j.payload.get("account_id"),
            }
            for j in session.scalars(
                select(LocalJob)
                .where(LocalJob.kind.like("social.%"))
                .order_by(LocalJob.created_at.desc())
                .limit(15)
            )
        ]
        attempts = [
            {
                "id": a.id,
                "postId": a.post_id,
                "revision": a.revision,
                "accountId": a.account_id,
                "status": a.status,
                "step": a.step,
                "errorCode": a.error_code,
                "remoteUrl": a.remote_url,
                "adapterVersion": a.adapter_version,
            }
            for a in session.scalars(
                select(BrowserPublishAttempt).order_by(BrowserPublishAttempt.updated_at.desc()).limit(30)
            )
        ]
        return {"accounts": accounts, "jobs": jobs, "attempts": attempts}


def finish_cancelled_operation(job_id: str) -> None:
    with write_session() as session:
        job = session.get(LocalJob, job_id)
        if job and job.kind.startswith("social.") and job.cancel_requested:
            job.status = "cancelled"
            job.completed_at = utc_now()
            job.locked_at = None
            job.lease_token = None
            job.lease_expires_at = None
            job.progress_message = "Browser operation cancelled."


def claim_attempt(post: dict[str, Any], adapter_version: str) -> str:
    key = f"{post['id']}:{post['revision']}:{post['browserAccountId']}"
    with write_session() as session:
        current = session.get(Post, post["id"])
        account = session.get(SocialBrowserAccount, post["browserAccountId"])
        if (
            current is None
            or current.status != "publishing"
            or not current.approved_at
            or current.revision != post["revision"]
            or current.browser_account_id != post["browserAccountId"]
        ):
            raise BrowserError("APPROVAL_REQUIRED", "An exact approved publish reservation is required.")
        if (
            account is None
            or account.status != "connected"
            or not account.identity
            or current.browser_account_identity != account.identity
            or account.platform != current.channel
        ):
            raise BrowserError("AUTH_REQUIRED", "Reconnect the exact account approved for this post.")
        attempt = session.scalar(select(BrowserPublishAttempt).where(BrowserPublishAttempt.key == key))
        if attempt and attempt.status != "safe_failed":
            raise BrowserError(
                "PUBLISH_REVIEW_REQUIRED",
                "This revision already has a publish attempt. Review its result; do not retry blindly.",
                uncertain=True,
            )
        if attempt is None:
            attempt = BrowserPublishAttempt(
                id=str(uuid4()),
                key=key,
                post_id=current.id,
                revision=current.revision,
                account_id=account.id,
                adapter_version=adapter_version,
                created_at=utc_now(),
            )
            session.add(attempt)
        attempt.status = "preparing"
        attempt.step = "checking_session"
        attempt.error_code = None
        attempt.updated_at = utc_now()
        session.flush()
        return attempt.id


def mark_click_intent(attempt_id: str) -> None:
    with write_session() as session:
        attempt = session.get(BrowserPublishAttempt, attempt_id)
        post = session.get(Post, attempt.post_id) if attempt else None
        account = session.get(SocialBrowserAccount, attempt.account_id) if attempt else None
        if (
            attempt is None
            or attempt.status != "preparing"
            or post is None
            or post.status != "publishing"
            or post.revision != attempt.revision
            or not post.approved_at
            or account is None
            or account.status != "connected"
            or post.browser_account_id != account.id
            or post.browser_account_identity != account.identity
        ):
            raise BrowserError("APPROVAL_REQUIRED", "Approval changed before the final publish action.")
        attempt.status = "click_intent"
        attempt.step = "publishing"
        attempt.updated_at = utc_now()
        append_audit(
            session,
            action="social.publish_intent",
            entity_type="post",
            entity_id=post.id,
            summary=f"Browser publish intent persisted for revision {post.revision}.",
        )


def finish_attempt(attempt_id: str, *, remote_url: str | None = None, error_code: str | None = None) -> None:
    with write_session() as session:
        attempt = session.get(BrowserPublishAttempt, attempt_id)
        if attempt is None:
            return
        if remote_url:
            attempt.status = "verified"
            attempt.step = "published"
            attempt.remote_url = remote_url
        elif attempt.status in {"click_intent", "uncertain", "verified"}:
            if attempt.status != "verified":
                attempt.status = "uncertain"
                attempt.step = "requires_review"
        else:
            attempt.status = "safe_failed"
            attempt.step = "stopped_before_publish"
        attempt.error_code = error_code
        attempt.updated_at = utc_now()


def recover_interrupted_attempts() -> None:
    with write_session() as session:
        for job in session.scalars(
            select(LocalJob).where(
                LocalJob.kind.in_(["social.connect", "social.verify"]),
                LocalJob.status.in_(["queued", "retrying", "running"]),
            )
        ):
            job.status = "cancelled"
            job.completed_at = utc_now()
            job.locked_at = None
            job.lease_token = None
            job.lease_expires_at = None
            job.progress_message = "Socium restarted. Open login or verify again when ready."
        for attempt in session.scalars(
            select(BrowserPublishAttempt).where(
                BrowserPublishAttempt.status.in_(["preparing", "click_intent"]),
            )
        ):
            attempt.status = "uncertain" if attempt.status == "click_intent" else "safe_failed"
            attempt.error_code = "PROCESS_INTERRUPTED"
            attempt.step = "requires_review"
            attempt.updated_at = utc_now()
