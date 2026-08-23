from __future__ import annotations

import asyncio
from contextlib import suppress
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
    expire_missed_jobs,
    fail_job,
    fail_publish_uncertain,
    finish_publish,
    image_provider_runtime,
    recover_stale_jobs,
    reserve_publish,
    scheduler_paused,
)


class LocalScheduler:
    def __init__(self, interval: float, catch_up_hours: int, stale_minutes: int) -> None:
        self.interval = interval
        self.catch_up_hours = catch_up_hours
        self.stale_minutes = stale_minutes
        self._task: asyncio.Task[None] | None = None
        self._wake = asyncio.Event()
        self._active = False
        self._status = "stopped"
        self._last_error: str | None = None

    def status(self) -> dict[str, Any]:
        return {
            "active": self._active,
            "status": self._status,
            "lastError": self._last_error,
            "catchUpHours": self.catch_up_hours,
        }

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._status = "starting"
            self._task = asyncio.create_task(self._run(), name="local-durable-scheduler")

    def wake(self) -> None:
        self._wake.set()

    def set_paused_state(self, paused: bool) -> None:
        self._active = False
        self._status = "paused" if paused else "idle"
        self._last_error = None
        self.wake()

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        self._active = False
        self._status = "stopped"

    async def _sleep(self) -> None:
        self._wake.clear()
        with suppress(TimeoutError):
            await asyncio.wait_for(self._wake.wait(), timeout=self.interval)

    async def _run(self) -> None:
        try:
            recover_stale_jobs(self.stale_minutes)
            while True:
                if scheduler_paused():
                    self._active = False
                    self._status = "paused"
                    self._last_error = None
                    await self._sleep()
                    continue

                expire_missed_jobs(self.catch_up_hours)
                job = claim_due_job()
                if job is None:
                    self._active = False
                    self._status = "idle"
                    self._last_error = None
                    await self._sleep()
                    continue

                self._active = True
                self._status = "running"
                await self._execute(job)
        except asyncio.CancelledError:
            self._active = False
            self._status = "stopped"
            raise
        except Exception as error:  # noqa: BLE001 - keep the local worker observable if its loop fails.
            self._active = False
            self._status = "error"
            self._last_error = str(error)[:500] or "The local scheduler stopped unexpectedly."

    async def _execute(self, job: dict[str, Any]) -> None:
        job_id = str(job["id"])
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
                    update_media_generation_progress(job_id, percent, message)

                def remote_ref(value: str) -> None:
                    update_media_generation_progress(
                        job_id,
                        20,
                        "Workflow queued in the image provider.",
                        remote_ref=value,
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
                update_media_generation_progress(job_id, 92, "Saving the verified image locally.")
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
                )
                self._last_error = None
            except GenerationCancelled:
                finish_cancelled_media_generation(job_id)
                self._last_error = None
            except Exception as error:  # noqa: BLE001 - generation is safe to retry locally.
                message = error.message if isinstance(error, AppError) else str(error) or "Image generation failed."
                if media_generation_cancel_requested(job_id):
                    finish_cancelled_media_generation(job_id)
                    self._last_error = None
                else:
                    fail_job(job_id, message, retryable=True)
                    self._last_error = message
            return
        if job.get("kind") == "seo.audit":
            payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
            url = str(payload.get("url") or "")
            try:
                result = await audit_website(url)
                save_seo_audit(result, trigger="scheduled")
                complete_job(job_id)
                self._last_error = None
            except Exception as error:  # noqa: BLE001 - read-only crawl failures are safe to retry.
                message = error.message if isinstance(error, AppError) else str(error) or "SEO audit failed."
                fail_job(job_id, message, retryable=True)
                self._last_error = message
            return
        if job.get("kind") != "post.publish":
            message = f"Unsupported local job kind: {job.get('kind')}"
            fail_job(job_id, message, retryable=False)
            self._last_error = message
            return

        payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
        post_id = str(payload.get("post_id") or "")
        revision = int(payload.get("revision") or 0)
        channel = str(payload.get("channel") or "")
        try:
            target = resolve_publish_target(channel)
        except AppError as error:
            fail_job(job_id, error.message, retryable=True)
            self._last_error = error.message
            return

        try:
            reserved = reserve_publish(post_id, revision)
        except AppError as error:
            fail_job(job_id, error.message, retryable=False)
            self._last_error = error.message
            return

        try:
            result = await publish_to_target(target, reserved)
            finish_publish(post_id, revision, result.remote_id, result.remote_url)
            complete_job(job_id)
            self._last_error = None
        except Exception as error:  # noqa: BLE001 - remote delivery failures may be ambiguous.
            message = (
                error.message if isinstance(error, AppError) else str(error) or "Scheduled publish failed."
            )
            fail_publish_uncertain(post_id, revision, message)
            fail_job(job_id, message, retryable=False)
            self._last_error = message
