from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse

from app import __version__
from app.config import get_settings
from app.connector_store import (
    create_connector,
    delete_connector,
    primary_connector_runtime,
    public_connector_state,
    update_connector,
)
from app.connectors.service import (
    send_saved_slack_approval,
    test_saved_connector,
)
from app.errors import AppError, ExternalServiceError
from app.lead_store import (
    clear_lead_score_override,
    icp_profile_state,
    import_leads,
    lead_summary,
    list_leads,
    restore_lead,
    save_icp_profile,
    suppress_lead,
    update_lead_compliance,
    update_lead_score_override,
    update_lead_status,
)
from app.media_job_store import (
    cancel_media_generation,
    list_media_generation_jobs,
    retry_media_generation,
    schedule_media_generation,
)
from app.media_store import (
    MAX_MEDIA_BYTES,
    create_generated_media_asset,
    create_media_asset,
    delete_media_asset,
    list_media_assets,
    media_asset_path,
    transform_media_asset,
    update_media_asset,
)
from app.outreach_store import (
    create_outreach_draft,
    decide_outreach_draft,
    delete_lead_data,
    edit_outreach_draft,
    export_lead_data,
    export_outreach_draft,
    list_outreach_drafts,
    outreach_generation_context,
)
from app.poller import TelegramPoller
from app.scheduler import LocalScheduler
from app.schemas import (
    ApprovalRequest,
    ConnectorAccountUpsert,
    DecisionRequest,
    EditPostRequest,
    GeneratePostRequest,
    GooglePlacesSearchRequest,
    IcpProfileUpdate,
    ImageGenerateRequest,
    ImageProviderUpdate,
    LeadComplianceUpdate,
    LeadDeleteRequest,
    LeadImportRequest,
    LeadScoreOverrideUpdate,
    LeadStatusUpdate,
    LeadSuppressionUpdate,
    MediaAssetUpdate,
    MediaTransformRequest,
    OutreachDecisionRequest,
    OutreachDraftUpdate,
    OutreachExportRequest,
    OutreachGenerateRequest,
    PollingUpdate,
    ProviderUpdate,
    PublishRequest,
    SchedulePostRequest,
    SchedulerUpdate,
    SeoAuditRequest,
    SeoAuditScheduleRequest,
    TelegramUpdate,
    WebsiteCrawlRequest,
    WorkspaceUpdate,
)
from app.seo_store import (
    cancel_seo_job,
    list_seo_audits,
    list_seo_jobs,
    retry_seo_job,
    save_seo_audit,
    schedule_seo_audit,
)
from app.seo_store import (
    get_seo_audit as load_seo_audit,
)
from app.services.crawler import crawl_website
from app.services.google_places import search_google_places
from app.services.image_generation import (
    generate_image,
    test_image_provider,
    validate_image_base_url,
)
from app.services.provider import (
    generate_content,
    generate_outreach,
    test_provider,
    validate_provider_base_url,
)
from app.services.publishing import publish_to_target, resolve_publish_target
from app.services.seo_audit import audit_website
from app.services.telegram import (
    delete_webhook,
    send_approval_request,
    test_connection,
)
from app.slack_listener import SlackSocketListener
from app.store import (
    cancel_job,
    create_post,
    decide_post,
    edit_post,
    fail_publish,
    fail_publish_uncertain,
    finish_publish,
    image_provider_runtime,
    initialize_storage,
    post_for_approval,
    provider_runtime,
    public_state,
    record_approval_sent,
    reserve_publish,
    retry_job,
    schedule_post,
    set_scheduler_paused,
    set_telegram_polling,
    telegram_runtime,
    update_image_provider,
    update_provider,
    update_telegram,
    update_workspace,
    workspace_runtime,
)

settings = get_settings()
telegram_poller = TelegramPoller(settings.telegram_poll_timeout)
slack_listener = SlackSocketListener(settings.slack_socket_enabled)
local_scheduler = LocalScheduler(
    settings.scheduler_interval,
    settings.scheduler_catch_up_hours,
    settings.scheduler_stale_minutes,
)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    initialize_storage()
    telegram_poller.start()
    slack_listener.start()
    local_scheduler.start()
    try:
        yield
    finally:
        await local_scheduler.stop()
        await slack_listener.stop()
        await telegram_poller.stop()


app = FastAPI(
    title="Socium Local API",
    description="Loopback-only API for the downloadable Socium application.",
    version=__version__,
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url=None,
)


@app.exception_handler(AppError)
async def app_error_handler(_request: Request, error: AppError) -> JSONResponse:
    return JSONResponse({"ok": False, "error": error.message}, status_code=error.status_code)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_request: Request, error: RequestValidationError) -> JSONResponse:
    details = error.errors()
    message = str(details[0].get("msg") or "Invalid request.") if details else "Invalid request."
    return JSONResponse({"ok": False, "error": message}, status_code=422)


def state_response() -> dict[str, Any]:
    state = public_state(telegram_poller.status(), local_scheduler.status())
    state["features"] = {
        "edition": "social-v1",
        "labsEnabled": settings.labs_enabled,
        "previewModules": ["lead-intelligence", "local-seo"] if settings.labs_enabled else [],
    }
    state["connectors"] = public_connector_state(slack_listener.statuses())
    state["leadSummary"] = lead_summary()
    state["icpProfile"] = icp_profile_state()
    return state


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "socium-api",
        "version": __version__,
        "mode": "local_only",
        "database": "sqlite",
    }


@app.get("/api/state")
def get_state() -> JSONResponse:
    return JSONResponse(state_response(), headers={"Cache-Control": "no-store"})


@app.get("/api/media")
def get_media_assets() -> JSONResponse:
    return JSONResponse(list_media_assets(), headers={"Cache-Control": "no-store"})


@app.post("/api/media")
async def upload_media_asset(file: Annotated[UploadFile, File()]) -> dict[str, Any]:
    data = await file.read(MAX_MEDIA_BYTES + 1)
    await file.close()
    if len(data) > MAX_MEDIA_BYTES:
        raise AppError("Images must be 10 MB or smaller.", 413)
    result = create_media_asset(data, file.filename)
    return {"ok": True, **result}


@app.post("/api/media/generate")
async def generate_media_asset(payload: ImageGenerateRequest) -> dict[str, Any]:
    generated = await generate_image(image_provider_runtime(), payload)
    result = create_generated_media_asset(
        generated.data,
        prompt=payload.prompt,
        negative_prompt=payload.negative_prompt,
        provider_kind=generated.provider_kind,
        model=generated.model,
        parameters=generated.parameters,
    )
    return {"ok": True, **result}


@app.get("/api/media/generations")
def get_media_generation_jobs(limit: int = 30) -> JSONResponse:
    if not 1 <= limit <= 100:
        raise AppError("Generation history limit must be between 1 and 100.")
    return JSONResponse(list_media_generation_jobs(limit), headers={"Cache-Control": "no-store"})


@app.post("/api/media/generations")
def queue_media_generation(payload: ImageGenerateRequest) -> dict[str, Any]:
    job = schedule_media_generation(payload, image_provider_runtime())
    local_scheduler.wake()
    return {"ok": True, "job": job}


@app.post("/api/media/generations/{job_id}/cancel")
def cancel_queued_media_generation(job_id: str) -> dict[str, Any]:
    job = cancel_media_generation(job_id)
    local_scheduler.wake()
    return {"ok": True, "job": job}


@app.post("/api/media/generations/{job_id}/retry")
def retry_queued_media_generation(job_id: str) -> dict[str, Any]:
    job = retry_media_generation(job_id)
    local_scheduler.wake()
    return {"ok": True, "job": job}


@app.get("/api/media/{asset_id}/content")
def get_media_content(asset_id: str) -> FileResponse:
    path, mime_type = media_asset_path(asset_id, "content")
    return FileResponse(
        path,
        media_type=mime_type,
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@app.get("/api/media/{asset_id}/preview")
def get_media_preview(asset_id: str) -> FileResponse:
    path, mime_type = media_asset_path(asset_id, "preview")
    return FileResponse(
        path,
        media_type=mime_type,
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@app.patch("/api/media/{asset_id}")
def change_media_asset(asset_id: str, payload: MediaAssetUpdate) -> dict[str, Any]:
    return {"ok": True, "asset": update_media_asset(asset_id, payload)}


@app.post("/api/media/{asset_id}/transform")
def create_media_transform(asset_id: str, payload: MediaTransformRequest) -> dict[str, Any]:
    result = transform_media_asset(asset_id, payload.preset)
    return {"ok": True, **result}


@app.delete("/api/media/{asset_id}")
def remove_media_asset(asset_id: str) -> dict[str, str | bool]:
    return {"ok": True, **delete_media_asset(asset_id)}


@app.get("/api/seo/audits")
def get_seo_audits(limit: int = 50) -> JSONResponse:
    if not 1 <= limit <= 100:
        raise AppError("SEO audit history limit must be between 1 and 100.")
    return JSONResponse(list_seo_audits(limit), headers={"Cache-Control": "no-store"})


@app.get("/api/seo/audits/{snapshot_id}")
def get_seo_audit(snapshot_id: str) -> JSONResponse:
    return JSONResponse(load_seo_audit(snapshot_id), headers={"Cache-Control": "no-store"})


@app.post("/api/seo/audits")
async def create_seo_audit(payload: SeoAuditRequest) -> dict[str, object]:
    result = await audit_website(payload.url)
    return {"ok": True, "audit": save_seo_audit(result, trigger="manual")}


@app.get("/api/seo/jobs")
def get_seo_schedules(limit: int = 50) -> JSONResponse:
    if not 1 <= limit <= 100:
        raise AppError("SEO schedule history limit must be between 1 and 100.")
    return JSONResponse(list_seo_jobs(limit), headers={"Cache-Control": "no-store"})


@app.post("/api/seo/jobs")
def create_seo_schedule(payload: SeoAuditScheduleRequest) -> dict[str, object]:
    job, created = schedule_seo_audit(payload, settings.scheduler_catch_up_hours)
    local_scheduler.wake()
    return {"ok": True, "job": job, "created": created}


@app.post("/api/seo/jobs/{job_id}/cancel")
def cancel_seo_schedule(job_id: str) -> dict[str, object]:
    return {"ok": True, "job": cancel_seo_job(job_id)}


@app.post("/api/seo/jobs/{job_id}/retry")
def retry_seo_schedule(job_id: str) -> dict[str, object]:
    job = retry_seo_job(job_id)
    local_scheduler.wake()
    return {"ok": True, "job": job}


@app.get("/api/leads")
def get_leads(
    query: str = "",
    status: str = "active",
    limit: int = 200,
    offset: int = 0,
) -> dict[str, object]:
    allowed_statuses = {
        "active",
        "high-intent",
        "outreach-ready",
        "retention-expired",
        "new",
        "qualified",
        "contacted",
        "archived",
        "suppressed",
    }
    if status not in allowed_statuses:
        raise AppError("Unknown lead status filter.")
    if not 1 <= limit <= 500 or offset < 0:
        raise AppError("Lead pagination values are invalid.")
    return list_leads(query=query[:200], status=status, limit=limit, offset=offset)


@app.post("/api/leads/import")
def create_lead_import(payload: LeadImportRequest) -> dict[str, Any]:
    result = import_leads(payload)
    return {"ok": True, "result": result, "state": state_response()}


@app.put("/api/leads/icp-profile")
def update_icp_profile(payload: IcpProfileUpdate) -> dict[str, Any]:
    result = save_icp_profile(payload)
    return {"ok": True, **result, "state": state_response()}


@app.post("/api/leads/discover/google-places")
async def discover_google_places(payload: GooglePlacesSearchRequest) -> JSONResponse:
    runtime = primary_connector_runtime("google-places", verified_only=True)
    results = await search_google_places(
        str(runtime["secrets"].get("api_key") or ""),
        payload.query,
        page_size=payload.page_size,
        language_code=str(runtime["config"].get("language_code") or ""),
        region_code=str(runtime["config"].get("region_code") or ""),
    )
    return JSONResponse(
        {
            "ok": True,
            "results": results,
            "storagePolicy": "transient",
            "attribution": "Google Maps",
        },
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/leads/crawl")
async def preview_website_lead(payload: WebsiteCrawlRequest) -> JSONResponse:
    result = await crawl_website(payload.url)
    return JSONResponse(
        {"ok": True, "result": result},
        headers={"Cache-Control": "no-store"},
    )


@app.patch("/api/leads/{lead_id}")
def change_lead_status(lead_id: str, payload: LeadStatusUpdate) -> dict[str, Any]:
    lead = update_lead_status(lead_id, payload)
    return {"ok": True, "lead": lead, "state": state_response()}


@app.post("/api/leads/{lead_id}/suppress")
def create_lead_suppression(lead_id: str, payload: LeadSuppressionUpdate) -> dict[str, Any]:
    lead = suppress_lead(lead_id, payload)
    return {"ok": True, "lead": lead, "state": state_response()}


@app.post("/api/leads/{lead_id}/restore")
def remove_lead_suppression(lead_id: str) -> dict[str, Any]:
    lead = restore_lead(lead_id)
    return {"ok": True, "lead": lead, "state": state_response()}


@app.put("/api/leads/{lead_id}/score-override")
def save_lead_score_override(lead_id: str, payload: LeadScoreOverrideUpdate) -> dict[str, Any]:
    lead = update_lead_score_override(lead_id, payload)
    return {"ok": True, "lead": lead, "state": state_response()}


@app.delete("/api/leads/{lead_id}/score-override")
def delete_lead_score_override(lead_id: str) -> dict[str, Any]:
    lead = clear_lead_score_override(lead_id)
    return {"ok": True, "lead": lead, "state": state_response()}


@app.put("/api/leads/{lead_id}/compliance")
def save_lead_compliance(lead_id: str, payload: LeadComplianceUpdate) -> dict[str, Any]:
    lead = update_lead_compliance(lead_id, payload)
    return {"ok": True, "lead": lead, "state": state_response()}


@app.get("/api/leads/{lead_id}/outreach-drafts")
def get_outreach_drafts(lead_id: str) -> dict[str, object]:
    return list_outreach_drafts(lead_id)


@app.post("/api/leads/{lead_id}/outreach-drafts")
async def generate_lead_outreach(lead_id: str, payload: OutreachGenerateRequest) -> dict[str, object]:
    provider = provider_runtime()
    if not provider["base_url"] or not provider["model"]:
        raise AppError("Connect an AI provider and select a model first.")
    lead = outreach_generation_context(lead_id)
    generated = await generate_outreach(provider, payload.model_dump(), lead, workspace_runtime())
    draft = create_outreach_draft(lead_id, payload, generated, provider)
    return {"ok": True, "draft": draft, "state": state_response()}


@app.put("/api/outreach-drafts/{draft_id}")
def update_outreach_draft(draft_id: str, payload: OutreachDraftUpdate) -> dict[str, object]:
    draft = edit_outreach_draft(draft_id, payload)
    return {"ok": True, "draft": draft, "state": state_response()}


@app.post("/api/outreach-drafts/{draft_id}/decision")
def save_outreach_decision(draft_id: str, payload: OutreachDecisionRequest) -> dict[str, object]:
    draft = decide_outreach_draft(draft_id, payload)
    return {"ok": True, "draft": draft, "state": state_response()}


@app.post("/api/outreach-drafts/{draft_id}/export")
def create_outreach_export(draft_id: str, payload: OutreachExportRequest) -> dict[str, object]:
    return {"ok": True, **export_outreach_draft(draft_id, payload.revision)}


@app.post("/api/leads/{lead_id}/data-export")
def create_lead_data_export(lead_id: str) -> dict[str, object]:
    return {"ok": True, **export_lead_data(lead_id)}


@app.delete("/api/leads/{lead_id}")
def delete_lead(lead_id: str, payload: LeadDeleteRequest) -> dict[str, object]:
    result = delete_lead_data(lead_id, payload)
    return {"ok": True, **result, "state": state_response()}


@app.put("/api/settings/workspace")
def save_workspace(payload: WorkspaceUpdate) -> dict[str, Any]:
    update_workspace(payload)
    return {"ok": True, "state": state_response()}


@app.put("/api/settings/provider")
def save_provider(payload: ProviderUpdate) -> dict[str, Any]:
    try:
        normalized_url = validate_provider_base_url(payload.kind, payload.base_url)
    except ExternalServiceError as error:
        raise AppError(error.message) from error
    update_provider(payload.model_copy(update={"base_url": normalized_url}))
    return {"ok": True, "state": state_response()}


@app.post("/api/providers/test")
async def provider_health() -> JSONResponse:
    result = await test_provider(provider_runtime())
    return JSONResponse(
        result.model_dump(by_alias=True, exclude_none=True),
        status_code=200 if result.ok else 502,
    )


@app.put("/api/settings/image-provider")
def save_image_provider(payload: ImageProviderUpdate) -> dict[str, Any]:
    try:
        normalized_url = validate_image_base_url(payload.base_url)
    except ExternalServiceError as error:
        raise AppError(error.message) from error
    update_image_provider(payload.model_copy(update={"base_url": normalized_url}))
    return {"ok": True, "state": state_response()}


@app.post("/api/image-providers/test")
async def image_provider_health() -> JSONResponse:
    result = await test_image_provider(image_provider_runtime())
    return JSONResponse(
        result.model_dump(by_alias=True, exclude_none=True),
        status_code=200 if result.ok else 502,
    )


@app.put("/api/settings/telegram")
async def save_telegram(payload: TelegramUpdate) -> dict[str, Any]:
    update_telegram(payload)
    await telegram_poller.refresh()
    return {"ok": True, "state": state_response()}


@app.post("/api/integrations/telegram/test")
async def telegram_health() -> dict[str, Any]:
    runtime = telegram_runtime()
    if not runtime["bot_token"]:
        raise AppError("Save a Telegram bot token first.")
    bot = await test_connection(str(runtime["bot_token"]))
    return {"ok": True, "message": f"Connected to {bot['name']}.", "bot": bot}


@app.put("/api/integrations/telegram/polling")
async def configure_polling(payload: PollingUpdate) -> dict[str, Any]:
    runtime = telegram_runtime()
    if payload.enabled:
        if not runtime["bot_token"] or not runtime["chat_id"]:
            raise AppError("Save and test Telegram before starting local approvals.")
        await test_connection(str(runtime["bot_token"]))
        await delete_webhook(str(runtime["bot_token"]))
    set_telegram_polling(payload.enabled)
    await telegram_poller.refresh()
    return {
        "ok": True,
        "message": "Local Telegram approvals started."
        if payload.enabled
        else "Local Telegram approvals stopped.",
        "state": state_response(),
    }


@app.post("/api/posts/generate")
async def generate_post(payload: GeneratePostRequest) -> dict[str, Any]:
    provider = provider_runtime()
    if not provider["base_url"] or not provider["model"]:
        raise AppError("Connect an AI provider and select a model first.")
    request_data = payload.model_dump()
    generated = await generate_content(provider, request_data, workspace_runtime())
    post = create_post(
        request=request_data,
        content=generated.model_dump(),
        provider=provider,
    )

    notifications: list[dict[str, Any]] = []
    notification: dict[str, Any] | None = None
    if payload.notify_telegram:
        try:
            telegram = telegram_runtime()
            if not telegram["bot_token"] or not telegram["chat_id"]:
                raise AppError("Telegram approval is not configured.")
            await send_approval_request(str(telegram["bot_token"]), str(telegram["chat_id"]), post)
            record_approval_sent(post["id"])
            notification = {"ok": True, "message": "Approval request sent to Telegram."}
        except AppError as error:
            notification = {"ok": False, "message": error.message}
        notifications.append({"channel": "telegram", **notification})
    if payload.notify_slack:
        try:
            await send_saved_slack_approval(post)
            record_approval_sent(post["id"], source="slack")
            notifications.append(
                {"channel": "slack", "ok": True, "message": "Approval request sent to Slack."}
            )
        except AppError as error:
            notifications.append({"channel": "slack", "ok": False, "message": error.message})
    return {
        "ok": True,
        "post": post,
        "notification": notification,
        "notifications": notifications,
        "state": state_response(),
    }


@app.patch("/api/posts/{post_id}")
def update_post(post_id: str, payload: EditPostRequest) -> dict[str, Any]:
    edit_post(post_id, payload)
    return {"ok": True, "state": state_response()}


@app.post("/api/posts/{post_id}/decision")
def post_decision(post_id: str, payload: DecisionRequest) -> dict[str, Any]:
    decide_post(post_id, payload.revision, payload.decision == "approve")
    return {"ok": True, "state": state_response()}


@app.post("/api/posts/{post_id}/approvals/slack")
async def request_slack_approval(post_id: str, payload: ApprovalRequest) -> dict[str, Any]:
    post = post_for_approval(post_id, payload.revision)
    delivery = await send_saved_slack_approval(post)
    record_approval_sent(post_id, source="slack")
    return {
        "ok": True,
        "delivery": delivery,
        "message": "Approval request sent to Slack.",
        "state": state_response(),
    }


@app.post("/api/posts/{post_id}/publish")
async def post_publish(post_id: str, payload: PublishRequest) -> dict[str, Any]:
    reserved = reserve_publish(post_id, payload.revision)
    try:
        target = resolve_publish_target(str(reserved["channel"]))
    except AppError as error:
        fail_publish(post_id, payload.revision, error.message)
        raise
    try:
        result = await publish_to_target(target, reserved)
        finish_publish(post_id, payload.revision, result.remote_id, result.remote_url)
    except Exception as error:
        message = error.message if isinstance(error, AppError) else "Publish failed."
        fail_publish_uncertain(post_id, payload.revision, message)
        raise
    return {"ok": True, "state": state_response()}


@app.post("/api/posts/{post_id}/schedule")
async def post_schedule(post_id: str, payload: SchedulePostRequest) -> dict[str, Any]:
    job, created = schedule_post(post_id, payload, settings.scheduler_catch_up_hours)
    local_scheduler.wake()
    return {
        "ok": True,
        "created": created,
        "job": job,
        "message": "Publish scheduled locally." if created else "This exact revision is already scheduled.",
        "state": state_response(),
    }


@app.post("/api/jobs/{job_id}/cancel")
async def job_cancel(job_id: str) -> dict[str, Any]:
    job = cancel_job(job_id)
    local_scheduler.wake()
    return {"ok": True, "job": job, "state": state_response()}


@app.post("/api/jobs/{job_id}/retry")
async def job_retry(job_id: str) -> dict[str, Any]:
    job = retry_job(job_id)
    local_scheduler.wake()
    return {"ok": True, "job": job, "state": state_response()}


@app.put("/api/scheduler")
async def scheduler_update(payload: SchedulerUpdate) -> dict[str, Any]:
    set_scheduler_paused(payload.paused)
    local_scheduler.set_paused_state(payload.paused)
    return {
        "ok": True,
        "message": "Local scheduler paused." if payload.paused else "Local scheduler resumed.",
        "state": state_response(),
    }


@app.get("/api/connectors")
def get_connectors() -> dict[str, Any]:
    return public_connector_state(slack_listener.statuses())


@app.post("/api/connectors")
def save_connector(payload: ConnectorAccountUpsert) -> dict[str, Any]:
    account = create_connector(payload)
    slack_listener.wake()
    return {"ok": True, "account": account, "state": state_response()}


@app.put("/api/connectors/{account_id}")
def replace_connector(account_id: str, payload: ConnectorAccountUpsert) -> dict[str, Any]:
    account = update_connector(account_id, payload)
    slack_listener.wake()
    return {"ok": True, "account": account, "state": state_response()}


@app.post("/api/connectors/{account_id}/test")
async def connector_health(account_id: str) -> dict[str, Any]:
    result = await test_saved_connector(account_id)
    slack_listener.wake()
    return {**result.public_dict(), "state": state_response()}


@app.delete("/api/connectors/{account_id}")
def remove_connector(account_id: str) -> dict[str, Any]:
    delete_connector(account_id)
    slack_listener.wake()
    return {"ok": True, "state": state_response()}
