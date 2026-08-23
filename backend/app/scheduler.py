from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

from app.errors import AppError
from app.media_job_store import (
    complete_media_generation_job,
    finish_cancelled_media_generation,
    media_generation_cancel_requested,
    update_media_generation_progress,
)
from app.media_store import create_generated_media_asset
from app.schemas import ImageGenerateRequest
from app.seo_store import save_seo_audit
from app.services.image_generation import GenerationCancelled, generate_image
from app.services.publishing import publish_to_target, resolve_publish_target
from app.services.seo_audit import audit_website
from app.store import (
    claim_due_job,
    complete_job,
    fail_job,
    fail_publish_uncertain,
    finish_publish,
    image_provider_runtime,
    next_job_run_at,
    publish_reservation_active,
    recover_stale_jobs,
    reserve_publish,
    scheduler_paused,
)


class LocalScheduler:
    def __init__(
        self,
        interval: float,
        catch_up_hours: int,
        stale_minutes: int,
        *,
        lease_seconds: int = 360,
        worker_timeout_seconds: int = 300,
        crash_limit: int = 3,
    ) -> None:
        self.crash_backoff_base = max(0.05, interval)
        self.catch_up_hours = catch_up_hours
        self.stale_minutes = stale_minutes
        self.lease_seconds = max(30, lease_seconds, worker_timeout_seconds + 30)
        self.worker_timeout_seconds = max(0.01, worker_timeout_seconds)
        self.crash_limit = max(1, crash_limit)
        self._task: asyncio.Task[None] | None = None
        self._worker_task: asyncio.Task[None] | None = None
        self._wake = asyncio.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._active = False
        self._status = "stopped"
        self._last_error: str | None = None
        self._next_wake_at: str | None = None
        self._idle_since: str | None = None
        self._crash_count = 0
        self._faulted = False
        self._loop_iterations = 0

    def status(self) -> dict[str, Any]:
        return {
            "active": self._active,
            "status": self._status,
            "lastError": self._last_error,
            "catchUpHours": self.catch_up_hours,
            "resourceMode": (
                "needs_attention"
                if self._faulted
                else "working"
                if self._active
                else "paused"
                if self._status == "paused"
                else "idle"
            ),
            "workerLimit": 1,
            "workersActive": 1 if self._worker_task is not None and not self._worker_task.done() else 0,
            "nextWakeAt": self._next_wake_at,
            "idleSince": self._idle_since,
            "crashCount": self._crash_count,
            "loopIterations": self._loop_iterations,
        }

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._loop = asyncio.get_running_loop()
            self._status = "starting"
            self._task = asyncio.create_task(self._run(), name="local-durable-scheduler")

    def wake(self) -> None:
        if self._loop is not None and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._wake.set)
        else:
            self._wake.set()

    def set_paused_state(self, paused: bool) -> None:
        self._active = False
        self._status = "paused" if paused else "idle"
        self._last_error = None
        if not paused:
            self._faulted = False
            self._crash_count = 0
        self.wake()

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        worker, self._worker_task = self._worker_task, None
        if worker is not None and not worker.done():
            worker.cancel()
            with suppress(asyncio.CancelledError):
                await worker
        self._active = False
        self._status = "stopped"
        self._next_wake_at = None
        self._loop = None

    async def _sleep(self, timeout: float | None = None) -> None:
        if timeout is None:
            await self._wake.wait()
            return
        if timeout <= 0:
            return
        with suppress(TimeoutError):
            await asyncio.wait_for(self._wake.wait(), timeout=timeout)

    @staticmethod
    def _seconds_until(value: str | None) -> float | None:
        if not value:
            return None
        parsed = datetime.fromisoformat(value)
        return max(0.0, (parsed.astimezone(UTC) - datetime.now(UTC)).total_seconds())

    async def _run(self) -> None:
        try:
            while True:
                self._wake.clear()
                if self._faulted:
                    self._active = False
                    self._status = "needs_attention"
                    self._next_wake_at = None
                    await self._sleep()
                    continue
                try:
                    await self._tick()
                    self._crash_count = 0
                except asyncio.CancelledError:
                    raise
                except Exception as error:  # noqa: BLE001 - supervisor crash-loop protection.
                    self._active = False
                    self._crash_count += 1
                    self._last_error = str(error)[:500] or "The local supervisor failed unexpectedly."
                    if self._crash_count >= self.crash_limit:
                        self._faulted = True
                        self._status = "needs_attention"
                        continue
                    self._status = "recovering"
                    await self._sleep(
                        min(30.0, self.crash_backoff_base * (2 ** (self._crash_count - 1)))
                    )
        except asyncio.CancelledError:
            self._active = False
            self._status = "stopped"
            raise

    async def _tick(self) -> None:
        self._loop_iterations += 1
        if scheduler_paused():
            self._active = False
            self._status = "paused"
            self._last_error = None
            self._next_wake_at = None
            self._idle_since = self._idle_since or datetime.now(UTC).isoformat()
            await self._sleep()
            return

        recover_stale_jobs(self.stale_minutes)
        job = claim_due_job(self.lease_seconds)
        if job is not None:
            self._active = True
            self._status = "running"
            self._last_error = None
            self._next_wake_at = None
            self._idle_since = None
            self._worker_task = asyncio.create_task(
                self._execute_bounded(job),
                name=f"local-worker-{str(job['id'])[:8]}",
            )
            try:
                await self._worker_task
            finally:
                self._worker_task = None
                self._active = False
            return

        self._active = False
        self._status = "idle"
        self._last_error = None
        self._idle_since = self._idle_since or datetime.now(UTC).isoformat()
        self._next_wake_at = next_job_run_at()
        await self._sleep(self._seconds_until(self._next_wake_at))

    async def _execute_bounded(self, job: dict[str, Any]) -> None:
        try:
            await asyncio.wait_for(self._execute(job), timeout=self.worker_timeout_seconds)
        except TimeoutError:
            job_id = str(job["id"])
            lease_token = str(job.get("leaseToken") or "") or None
            message = f"Local worker exceeded the {self.worker_timeout_seconds}-second safety timeout."
            if job.get("kind") == "post.publish":
                payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
                post_id = str(payload.get("post_id") or "")
                revision = int(payload.get("revision") or 0)
                reserved = publish_reservation_active(post_id, revision)
                if reserved:
                    fail_publish_uncertain(post_id, revision, message)
                fail_job(job_id, message, retryable=not reserved, lease_token=lease_token)
            else:
                fail_job(
                    job_id,
                    message,
                    retryable=job.get("kind") == "seo.audit",
                    lease_token=lease_token,
                )
            self._last_error = message

    async def _execute(self, job: dict[str, Any]) -> None:
        job_id = str(job["id"])
        lease_token = str(job.get("leaseToken") or "") or None
        if job.get("kind") == "media.generate":
            payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
            request_payload = payload.get("request") if isinstance(payload.get("request"), dict) else {}
            provider_snapshot = (
                payload.get("provider") if isinstance(payload.get("provider"), dict) else {}
            )
            try:
                provider = image_provider_runtime()
                if provider.get("updated_at") != provider_snapshot.get("updated_at"):
                    raise AppError(
                        "Image provider settings changed after this job was queued; retry to use the new settings."
                    )
                request = ImageGenerateRequest.model_validate(request_payload)

                def progress(percent: int, message: str) -> None:
                    update_media_generation_progress(
                        job_id,
                        percent,
                        message,
                        lease_token=lease_token,
                    )

                def remote_ref(value: str) -> None:
                    update_media_generation_progress(
                        job_id,
                        20,
                        "Workflow queued in the image provider.",
                        remote_ref=value,
                        lease_token=lease_token,
                    )

                generated = await generate_image(
                    provider,
                    request,
                    progress=progress,
                    cancel_check=lambda: media_generation_cancel_requested(job_id),
                    remote_ref=remote_ref,
                )
                if media_generation_cancel_requested(job_id):
                    raise GenerationCancelled
                update_media_generation_progress(
                    job_id,
                    92,
                    "Saving the verified image locally.",
                    lease_token=lease_token,
                )
                result = create_generated_media_asset(
                    generated.data,
                    prompt=request.prompt,
                    negative_prompt=request.negative_prompt,
                    alt_text=request.alt_text,
                    provider_kind=generated.provider_kind,
                    model=generated.model,
                    parameters=generated.parameters,
                )
                complete_media_generation_job(
                    job_id,
                    str(result["asset"]["id"]),
                    bool(result["deduplicated"]),
                    lease_token,
                )
                self._last_error = None
            except GenerationCancelled:
                finish_cancelled_media_generation(job_id, lease_token)
                self._last_error = None
            except Exception as error:  # noqa: BLE001 - generation is safe to retry locally.
                message = error.message if isinstance(error, AppError) else str(error) or "Image generation failed."
                if media_generation_cancel_requested(job_id):
                    finish_cancelled_media_generation(job_id, lease_token)
                    self._last_error = None
                else:
                    fail_job(job_id, message, retryable=True, lease_token=lease_token)
                    self._last_error = message
            return
        if job.get("kind") == "seo.audit":
            payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
            url = str(payload.get("url") or "")
            try:
                result = await audit_website(url)
                save_seo_audit(result, trigger="scheduled")
                complete_job(job_id, lease_token)
                self._last_error = None
            except Exception as error:  # noqa: BLE001 - read-only crawl failures are safe to retry.
                message = error.message if isinstance(error, AppError) else str(error) or "SEO audit failed."
                fail_job(job_id, message, retryable=True, lease_token=lease_token)
                self._last_error = message
            return
        if job.get("kind") != "post.publish":
            message = f"Unsupported local job kind: {job.get('kind')}"
            fail_job(job_id, message, retryable=False, lease_token=lease_token)
            self._last_error = message
            return

        payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
        post_id = str(payload.get("post_id") or "")
        revision = int(payload.get("revision") or 0)
        channel = str(payload.get("channel") or "")
        try:
            target = resolve_publish_target(channel)
        except AppError as error:
            fail_job(job_id, error.message, retryable=True, lease_token=lease_token)
            self._last_error = error.message
            return

        try:
            reserved = reserve_publish(post_id, revision)
        except AppError as error:
            fail_job(job_id, error.message, retryable=False, lease_token=lease_token)
            self._last_error = error.message
            return

        try:
            result = await publish_to_target(target, reserved)
            finish_publish(post_id, revision, result.remote_id, result.remote_url)
            complete_job(job_id, lease_token)
            self._last_error = None
        except Exception as error:  # noqa: BLE001 - remote delivery failures may be ambiguous.
            message = (
                error.message if isinstance(error, AppError) else str(error) or "Scheduled publish failed."
            )
            fail_publish_uncertain(post_id, revision, message)
            fail_job(job_id, message, retryable=False, lease_token=lease_token)
            self._last_error = message
