from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import perf_counter
from typing import Annotated, Any
from urllib.parse import urlsplit

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse

from app import __version__
from app.approval_actions import regenerate_image_revision, regenerate_post_revision
from app.backup_service import create_backup, list_backups
from app.business_os_store import (
    business_profile,
    create_knowledge_source,
    create_workflow,
    dashboard_summary,
    delete_knowledge_source,
    knowledge_state,
    list_ai_decisions,
    list_approvals,
    list_inbox,
    list_workflows,
    record_ai_decision,
    record_knowledge_analysis,
    run_workflow,
    update_inbox_item,
    update_knowledge_item,
)
from app.business_os_store import (
    decide_approval as decide_generic_approval,
)
from app.config import get_settings
from app.connector_store import (
    connector_runtime,
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
from app.content_job_store import (
    cancel_content_generation,
    get_content_generation,
    list_content_generations,
    schedule_content_generation,
)
from app.content_service import generate_content_draft
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
from app.lifecycle_service import (
    UpdateMonitor,
    check_for_updates,
    lifecycle_state,
    prepare_update_stream,
    request_controller_action,
    request_storage_move,
    runtime_controller_available,
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
    create_website_media_asset,
    delete_media_asset,
    list_media_assets,
    media_asset_path,
    purge_previous_brand_media,
    transform_media_asset,
    update_media_asset,
)
from app.native_storage import pick_storage_directory, validate_storage_destination
from app.oauth_broker import callback_html, oauth_broker
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
from app.runtime_signals import register_scheduler_wake
from app.scheduler import LocalScheduler
from app.schemas import (
    ApprovalRequest,
    AutomationRuleUpsert,
    BrandDiscoveryDraft,
    BrandDiscoveryRequest,
    BrandProfileUpdate,
    ConnectorAccountUpsert,
    DecisionRequest,
    EditPostRequest,
    GeneratePostRequest,
    GenericApprovalDecision,
    GooglePlacesSearchRequest,
    IcpProfileUpdate,
    ImageGenerateRequest,
    ImageProviderUpdate,
    InboxItemUpdate,
    JobRecoveryRequest,
    KnowledgeAnalyzeRequest,
    KnowledgeItemUpdate,
    KnowledgeSourceCreate,
    LeadComplianceUpdate,
    LeadDeleteRequest,
    LeadImportRequest,
    LeadScoreOverrideUpdate,
    LeadStatusUpdate,
    LeadSuppressionUpdate,
    LocalModelPullRequest,
    MediaAssetUpdate,
    MediaTransformRequest,
    OnboardingUpdate,
    OutreachDecisionRequest,
    OutreachDraftUpdate,
    OutreachExportRequest,
    OutreachGenerateRequest,
    PollingUpdate,
    PreviousBrandCleanupRequest,
    ProviderDiscoveryRequest,
    ProviderUpdate,
    PublishRequest,
    RevisionRequest,
    SchedulePostRequest,
    SchedulerUpdate,
    SeoAuditRequest,
    SeoAuditScheduleRequest,
    StorageDirectoryPickerRequest,
    StorageMoveRequest,
    TelegramConnectRequest,
    TelegramProxyTestRequest,
    TelegramUpdate,
    WebsiteCrawlRequest,
    WorkflowDefinitionCreate,
    WorkflowRunCreate,
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
from app.services.crawler import crawl_brand_website, crawl_website, download_public_brand_image
from app.services.google_places import search_google_places
from app.services.image_generation import (
    generate_image,
    test_image_provider,
    validate_image_base_url,
)
from app.services.local_ai import local_ai_status, stream_ollama_pull
from app.services.provider import (
    discover_brand_profile,
    discover_provider,
    generate_outreach,
    test_provider,
    validate_provider_base_url,
)
from app.services.publishing import publish_to_target, resolve_publish_target
from app.services.seo_audit import audit_website
from app.services.telegram import (
    delete_webhook,
    discover_recent_chat,
    resolve_chat,
    test_connection,
    test_proxy_connection,
    validate_proxy_url,
)
from app.slack_listener import SlackSocketListener
from app.storage_health import storage_state
from app.store import (
    acknowledge_remote_edit,
    cancel_job,
    complete_telegram_connection,
    create_approval_action,
    create_automation,
    decide_post,
    delete_automation,
    delete_previous_brand_data,
    duplicate_automation,
    edit_post,
    ensure_automation_jobs,
    fail_approval_delivery,
    fail_publish,
    fail_publish_uncertain,
    finish_publish,
    image_provider_runtime,
    initialize_storage,
    onboarding_state,
    post_for_approval,
    previous_brand_data_summary,
    primary_image_runtime,
    provider_runtime,
    public_state,
    record_approval_sent,
    record_provider_verified,
    recover_missed_job,
    reserve_publish,
    retry_job,
    save_telegram_token,
    schedule_post,
    set_scheduler_paused,
    set_telegram_polling,
    telegram_runtime,
    update_automation,
    update_brand_profile,
    update_image_provider,
    update_onboarding,
    update_provider,
    update_telegram,
    update_telegram_proxy,
    update_workspace,
    workspace_runtime,
)

settings = get_settings()
telegram_poller = TelegramPoller(settings.telegram_poll_timeout)
slack_listener = SlackSocketListener(settings.slack_socket_enabled, settings.connect_broker_url)
local_scheduler = LocalScheduler(
    settings.scheduler_interval,
    settings.scheduler_catch_up_hours,
    settings.scheduler_stale_minutes,
    lease_seconds=settings.scheduler_lease_seconds,
    worker_timeout_seconds=settings.scheduler_worker_timeout_seconds,
    crash_limit=settings.scheduler_crash_limit,
    approval_wake=lambda: (telegram_poller.wake(), slack_listener.wake()),
)
register_scheduler_wake(local_scheduler.wake)
update_monitor = UpdateMonitor(lambda: not bool(local_scheduler.status().get("workersActive")))


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    initialize_storage()
    if settings.migration_check:
        yield
        return
    ensure_automation_jobs()
    telegram_poller.start()
    slack_listener.start()
    local_scheduler.start()
    update_monitor.start()
    try:
        yield
    finally:
        await update_monitor.stop()
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
        "edition": "business-os-v1.4",
        "labsEnabled": settings.labs_enabled,
        "previewModules": ["lead-intelligence", "local-seo"] if settings.labs_enabled else [],
        "businessOs": True,
        "knowledge": True,
        "unifiedInbox": True,
        "genericWorkflows": True,
    }
    state["connectors"] = public_connector_state(slack_listener.statuses())
    state["connectors"]["oneClickConfigured"] = oauth_broker.configured()
    state["leadSummary"] = lead_summary()
    state["icpProfile"] = icp_profile_state()
    state["storage"] = storage_state()
    state["onboarding"] = onboarding_state(state["storage"])
    state["lifecycle"] = lifecycle_state()
    state["backups"] = list_backups()
    return state


def _brand_page_text(evidence: dict[str, object]) -> str:
    pages = evidence.get("pages")
    if not isinstance(pages, list):
        return ""
    sections: list[str] = []
    for page in pages:
        if not isinstance(page, dict):
            continue
        for key in ("title", "description", "text"):
            value = page.get(key)
            if isinstance(value, str) and value.strip():
                sections.append(value.strip())
    return " ".join(sections)[:24_000]


def _brand_title_descriptor(evidence: dict[str, object], business_name: str) -> str:
    pages = evidence.get("pages")
    if not isinstance(pages, list):
        return ""
    ignored = {"home", "official site", "official website", business_name.casefold()}
    for page in pages:
        if not isinstance(page, dict):
            continue
        title = str(page.get("title") or "")
        parts = re.split(r"\s*(?:\||—|–)\s*|\s+-\s+", title)
        for part in parts:
            clean = " ".join(part.split()).strip(" .:-")
            if len(clean) >= 5 and clean.casefold() not in ignored:
                return clean[:160]
    return ""


def _brand_description(evidence: dict[str, object], business_name: str, descriptor: str) -> str:
    supplied = str(evidence.get("description") or "").strip()
    if supplied:
        return supplied[:2_000]
    text = _brand_page_text(evidence)
    if business_name:
        statement = re.search(
            rf"\b{re.escape(business_name)}\b\s+"
            r"(?:is|provides|offers|helps|builds|delivers)\s+[^.!?]{20,700}[.!?]",
            text,
            re.IGNORECASE,
        )
        if statement:
            return " ".join(statement.group(0).split())[:2_000]
    if descriptor:
        return f"{business_name or 'This business'} provides {descriptor.lower()}."[:2_000]
    return ""


def _brand_industry(evidence_text: str, descriptor: str) -> str:
    haystack = f"{descriptor} {evidence_text}".casefold()
    mappings = (
        (("workforce", "analytics"), "Workforce analytics software"),
        (("human resources",), "Human resources technology"),
        (("marketing",), "Marketing and advertising"),
        (("ecommerce",), "E-commerce"),
        (("real estate",), "Real estate"),
        (("healthcare",), "Healthcare"),
        (("financial",), "Financial services"),
        (("software",), "Software / SaaS"),
        (("saas",), "Software / SaaS"),
        (("restaurant",), "Food and hospitality"),
        (("education",), "Education"),
    )
    for needles, label in mappings:
        if all(needle in haystack for needle in needles):
            return label
    return descriptor[:160]


def _brand_target_audience(industry: str, descriptor: str) -> str:
    identity = f"{industry} {descriptor}".casefold()
    if "workforce" in identity or "human resources" in identity:
        return "Enterprise HR, people operations, and workforce leaders."
    if "marketing" in identity:
        return "Businesses and marketing teams seeking practical growth support."
    if "e-commerce" in identity:
        return "Online retailers and commerce teams."
    if "software" in identity or "saas" in identity:
        return "Organizations evaluating software to improve their operations."
    if descriptor:
        return f"Organizations looking for {descriptor.lower()}."[:3_000]
    return "Potential customers researching the business and its services."


def _brand_hashtag(business_name: str) -> str:
    hashtag = re.sub(r"[^A-Za-z0-9_]", "", business_name)
    return f"#{hashtag[:60]}" if hashtag else ""


def _brand_draft_from_website_evidence(evidence: dict[str, object]) -> BrandDiscoveryDraft:
    colors = [str(item) for item in evidence.get("colors", []) if isinstance(item, str)]
    fonts = [str(item) for item in evidence.get("fonts", []) if isinstance(item, str)]
    business_name = str(evidence.get("businessName") or "")[:120]
    evidence_text = _brand_page_text(evidence)
    descriptor = _brand_title_descriptor(evidence, business_name)
    description = _brand_description(evidence, business_name, descriptor)
    industry = _brand_industry(evidence_text, descriptor)
    target_audience = _brand_target_audience(industry, descriptor)
    product_label = descriptor or industry or description
    products_services = (
        f"{product_label.rstrip('.')} platform and related services." if product_label else description
    )[:4_000]
    hashtag = _brand_hashtag(business_name)
    visual_style = "Use the website-derived brand palette with clean, professional layouts" + (
        f" and {fonts[0]} typography." if fonts else "."
    )
    return BrandDiscoveryDraft(
        business_name=business_name,
        website=str(evidence.get("website") or "")[:2_048],
        description=description,
        industry=industry,
        products_services=products_services,
        target_audience=target_audience,
        location=str(evidence.get("location") or "")[:240],
        goals=[
            "Build consistent brand awareness",
            "Educate potential customers",
            "Generate qualified conversations",
        ],
        call_to_action=f"Explore {business_name or 'the business'} and learn more.",
        content_pillars=[value for value in (industry, descriptor, "Customer education") if value],
        branded_hashtags=[hashtag] if hashtag else [],
        primary_color=colors[0] if colors else "#f59e0b",
        secondary_color=colors[1] if len(colors) > 1 else "#18181b",
        accent_color=colors[2] if len(colors) > 2 else "#10b981",
        heading_font=fonts[0] if fonts else "",
        body_font=fonts[1] if len(fonts) > 1 else (fonts[0] if fonts else ""),
        visual_style=visual_style[:2_000],
    )


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


@app.get("/api/workspaces/{workspace_id}/business")
def get_business_profile(workspace_id: int) -> dict[str, Any]:
    return {"ok": True, "profile": business_profile(workspace_id)}


@app.get("/api/workspaces/{workspace_id}/knowledge")
def get_knowledge(
    workspace_id: int,
    status: str | None = None,
    query: str | None = None,
) -> dict[str, Any]:
    return {
        "ok": True,
        **knowledge_state(workspace_id, status=status, query=query),
    }


@app.post("/api/workspaces/{workspace_id}/knowledge/sources")
def add_knowledge_source(workspace_id: int, payload: KnowledgeSourceCreate) -> dict[str, Any]:
    normalized = payload.model_copy(update={"workspace_id": workspace_id})
    return {"ok": True, "source": create_knowledge_source(normalized)}


@app.patch("/api/workspaces/{workspace_id}/knowledge/items/{item_id}")
def review_knowledge_item(
    workspace_id: int,
    item_id: str,
    payload: KnowledgeItemUpdate,
) -> dict[str, Any]:
    current = knowledge_state(workspace_id)
    if not any(item["id"] == item_id for item in current["items"]):
        raise AppError("Knowledge fact not found in this workspace.", 404)
    return {"ok": True, "item": update_knowledge_item(item_id, payload)}


@app.delete("/api/workspaces/{workspace_id}/knowledge/sources/{source_id}")
def remove_knowledge_source(workspace_id: int, source_id: str) -> dict[str, Any]:
    current = knowledge_state(workspace_id)
    if not any(source["id"] == source_id for source in current["sources"]):
        raise AppError("Knowledge source not found in this workspace.", 404)
    delete_knowledge_source(source_id)
    return {"ok": True}


@app.get("/api/workflows")
def get_workflows(workspace_id: int = 1) -> dict[str, Any]:
    return {"ok": True, "items": list_workflows(workspace_id)}


@app.post("/api/workflows")
def add_workflow(payload: WorkflowDefinitionCreate) -> dict[str, Any]:
    return {"ok": True, "workflow": create_workflow(payload)}


@app.post("/api/workflows/{workflow_id}/runs")
def start_workflow(workflow_id: str, payload: WorkflowRunCreate) -> dict[str, Any]:
    return {"ok": True, "run": run_workflow(workflow_id, payload)}


@app.get("/api/approvals")
def get_approvals(workspace_id: int = 1, status: str | None = None) -> dict[str, Any]:
    return {"ok": True, "items": list_approvals(workspace_id, status)}


@app.post("/api/approvals/{approval_id}/decision")
def decide_approval_request(
    approval_id: str,
    payload: GenericApprovalDecision,
) -> dict[str, Any]:
    return {"ok": True, "approval": decide_generic_approval(approval_id, payload)}


@app.get("/api/inbox")
def get_inbox(workspace_id: int = 1, status: str | None = "open") -> dict[str, Any]:
    return {"ok": True, "items": list_inbox(workspace_id, status)}


@app.patch("/api/inbox/{item_id}")
def change_inbox_item(item_id: str, payload: InboxItemUpdate) -> dict[str, Any]:
    return {"ok": True, "item": update_inbox_item(item_id, payload)}


@app.get("/api/dashboard/summary")
def get_dashboard_summary(workspace_id: int = 1) -> JSONResponse:
    return JSONResponse(
        {"ok": True, "summary": dashboard_summary(workspace_id)},
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/ai/decisions")
def get_ai_decisions(workspace_id: int = 1, limit: int = 100) -> dict[str, Any]:
    return {"ok": True, "items": list_ai_decisions(workspace_id, limit)}


@app.get("/api/storage")
def get_storage() -> JSONResponse:
    return JSONResponse(storage_state(refresh=True), headers={"Cache-Control": "no-store"})


@app.post("/api/storage/pick-directory")
async def pick_storage(payload: StorageDirectoryPickerRequest) -> dict[str, Any]:
    selected = await asyncio.to_thread(pick_storage_directory, payload.purpose)
    return {"ok": True, "cancelled": selected is None, "path": selected}


@app.post("/api/storage/move")
def move_storage(payload: StorageMoveRequest) -> dict[str, Any]:
    data_directory = validate_storage_destination(payload.data_dir, "data")
    models_directory = validate_storage_destination(payload.models_dir, "models")
    if (
        data_directory == models_directory
        or data_directory in models_directory.parents
        or models_directory in data_directory.parents
    ):
        raise AppError("Data and local AI models must use separate folders.")
    result = request_storage_move(str(data_directory), str(models_directory))
    return {"ok": True, **result}


@app.get("/api/lifecycle")
def get_lifecycle() -> JSONResponse:
    return JSONResponse(
        {"lifecycle": lifecycle_state(), "backups": list_backups()},
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/lifecycle/check")
def check_update() -> dict[str, Any]:
    return {"ok": True, "lifecycle": check_for_updates(force=True)}


@app.post("/api/lifecycle/backup")
def backup_now() -> dict[str, Any]:
    return {"ok": True, "backup": create_backup(), "backups": list_backups()}


@app.post("/api/lifecycle/prepare")
def prepare_update() -> StreamingResponse:
    if local_scheduler.status().get("workersActive"):
        raise AppError(
            "Socium is finishing an active job. Try the update again when the scheduler is idle.",
            status_code=409,
        )
    return StreamingResponse(prepare_update_stream(), media_type="application/x-ndjson")


@app.post("/api/lifecycle/{action}")
def lifecycle_action(action: str) -> dict[str, Any]:
    if (
        action in {"update", "rollback"}
        and runtime_controller_available()
        and local_scheduler.status().get("workersActive")
    ):
        raise AppError(
            "Socium is finishing an active job. Try the update again when the scheduler is idle.",
            status_code=409,
        )
    return request_controller_action(action)


@app.put("/api/onboarding")
def save_onboarding(payload: OnboardingUpdate) -> dict[str, Any]:
    current_storage = storage_state(refresh=payload.action == "confirm-storage")
    update_onboarding(payload, current_storage)
    return {"ok": True, "state": state_response()}


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
    generated = await generate_image(primary_image_runtime(), payload)
    result = create_generated_media_asset(
        generated.data,
        prompt=payload.prompt,
        negative_prompt=payload.negative_prompt,
        alt_text=payload.alt_text,
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
    job = schedule_media_generation(payload, primary_image_runtime())
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


@app.put("/api/settings/brand-profile")
def save_brand_profile(payload: BrandProfileUpdate) -> dict[str, Any]:
    update_brand_profile(payload)
    return {"ok": True, "state": state_response()}


@app.get("/api/settings/brand-profile/history")
def get_previous_brand_history() -> dict[str, Any]:
    return {"ok": True, "summary": previous_brand_data_summary()}


@app.delete("/api/settings/brand-profile/history")
def remove_previous_brand_history(payload: PreviousBrandCleanupRequest) -> dict[str, Any]:
    summary = delete_previous_brand_data(payload.current_business_name)
    deleted_media = purge_previous_brand_media(summary.pop("_mediaIds", []))
    public_summary = {key: value for key, value in summary.items() if not key.startswith("_")}
    public_summary["mediaAssets"] = deleted_media
    return {"ok": True, "deleted": public_summary, "state": state_response()}


async def _analyze_brand_source(url: str, workspace_id: int = 1) -> dict[str, Any]:
    evidence = await crawl_brand_website(url)
    runtime = provider_runtime()
    warnings: list[str] = []
    ai_enhanced = True
    started = perf_counter()
    try:
        draft = await discover_brand_profile(runtime, evidence)
        record_ai_decision(
            purpose="knowledge.extract",
            provider_kind=str(runtime["kind"]),
            model=str(runtime["model"]),
            status="completed",
            duration_ms=round((perf_counter() - started) * 1_000),
            context_refs=[{"type": "website", "url": url}],
            workspace_id=workspace_id,
        )
    except ExternalServiceError as error:
        ai_enhanced = False
        draft = _brand_draft_from_website_evidence(evidence)
        record_ai_decision(
            purpose="knowledge.extract",
            provider_kind=str(runtime["kind"]),
            model=str(runtime["model"]),
            status="failed",
            duration_ms=round((perf_counter() - started) * 1_000),
            context_refs=[{"type": "website", "url": url}],
            error=error.message,
            workspace_id=workspace_id,
        )
        warnings.append(
            "AI enhancement is temporarily unavailable. Socium filled website facts and editable "
            "fallback suggestions; review the draft or select Analyze & fill again later."
        )
    logo_asset: dict[str, Any] | None = None
    logo_candidates = [str(item) for item in evidence.get("logoCandidates", []) if isinstance(item, str)]
    for candidate in logo_candidates[:3]:
        try:
            downloaded = await download_public_brand_image(candidate)
            if downloaded.status_code >= 400 or not downloaded.content:
                continue
            filename = (urlsplit(downloaded.final_url).path.rsplit("/", 1)[-1] or "website-logo")[:255]
            logo_asset = create_website_media_asset(downloaded.content, filename, downloaded.final_url)[
                "asset"
            ]
            break
        except (AppError, ExternalServiceError):
            continue
    if logo_candidates and logo_asset is None:
        warnings.append("A logo was detected but could not be imported as a safe PNG, JPEG, or WebP file.")
    pages = evidence.get("pages", []) if isinstance(evidence.get("pages"), list) else []
    website_fields = {
        "businessName",
        "website",
        "description",
        "location",
        "primaryColor",
        "secondaryColor",
        "accentColor",
        "headingFont",
        "bodyFont",
    }
    draft_data = draft.model_dump(by_alias=True)
    origins = {}
    for key, value in draft_data.items():
        if key in website_fields and value:
            origins[key] = "website"
        elif value:
            origins[key] = "ai-suggestion" if ai_enhanced else "website-suggestion"
        else:
            origins[key] = "not-found"
    source_rows = [
        {"url": str(page.get("url", "")), "title": str(page.get("title", ""))}
        for page in pages
        if isinstance(page, dict)
    ]
    knowledge = record_knowledge_analysis(
        workspace_id=workspace_id,
        url=url,
        draft=draft_data,
        field_origins=origins,
        sources=source_rows,
    )
    return {
        "ok": True,
        "draft": draft_data,
        "fieldOrigins": origins,
        "sources": source_rows,
        "signals": {
            "colors": evidence.get("colors", []),
            "fonts": evidence.get("fonts", []),
            "logoCandidates": logo_candidates,
            "socialLinks": evidence.get("socialLinks", []),
        },
        "logoAsset": logo_asset,
        "provider": {
            "kind": runtime["kind"],
            "model": runtime["model"],
            "local": runtime["kind"] == "ollama",
        },
        "warnings": warnings,
        "knowledge": knowledge,
        "storagePolicy": "editable-draft",
    }


@app.post("/api/settings/brand-profile/discover")
async def discover_brand(payload: BrandDiscoveryRequest) -> JSONResponse:
    return JSONResponse(
        await _analyze_brand_source(payload.url),
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/workspaces/{workspace_id}/knowledge/analyze")
async def analyze_knowledge_source(
    workspace_id: int,
    payload: KnowledgeAnalyzeRequest,
) -> JSONResponse:
    return JSONResponse(
        await _analyze_brand_source(payload.url, workspace_id),
        headers={"Cache-Control": "no-store"},
    )


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
    runtime = provider_runtime()
    result = await test_provider(runtime)
    if result.ok and runtime["model"]:
        record_provider_verified()
    return JSONResponse(
        result.model_dump(by_alias=True, exclude_none=True),
        status_code=200 if result.ok else 502,
    )


@app.post("/api/providers/discover")
async def provider_discovery(payload: ProviderDiscoveryRequest) -> dict[str, Any]:
    try:
        return await discover_provider(payload.base_url, payload.protocol_hint, payload.api_key)
    except ExternalServiceError as error:
        raise AppError(error.message) from error


@app.get("/api/providers/local/status")
async def get_local_ai_status(base_url: str = "http://127.0.0.1:11434") -> dict[str, Any]:
    try:
        return await local_ai_status(base_url)
    except ExternalServiceError as error:
        raise AppError(error.message) from error


@app.post("/api/providers/local/pull")
async def pull_local_model(payload: LocalModelPullRequest) -> StreamingResponse:
    try:
        status = await local_ai_status(payload.base_url)
    except ExternalServiceError as error:
        raise AppError(error.message) from error
    if not status["ollamaRunning"]:
        raise AppError("Ollama is not running. Start Ollama, then try the download again.", 502)
    return StreamingResponse(
        stream_ollama_pull(payload.base_url, payload.model),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
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
    bot = await test_connection(
        str(runtime["bot_token"]),
        str(runtime.get("proxy_url") or ""),
    )
    return {"ok": True, "message": f"Connected to {bot['name']}.", "bot": bot}


@app.post("/api/integrations/telegram/proxy/test")
async def telegram_proxy_health(payload: TelegramProxyTestRequest) -> dict[str, Any]:
    runtime = telegram_runtime()
    proxy_url = payload.proxy_url.strip() or str(runtime.get("proxy_url") or "")
    if not proxy_url:
        raise AppError("Enter your HTTP or SOCKS5 proxy URL first.")
    try:
        await test_proxy_connection(proxy_url)
    except ExternalServiceError as error:
        raise AppError(error.message, 502) from error
    return {
        "ok": True,
        "message": "Proxy reached the Telegram Bot API successfully.",
    }


@app.post("/api/integrations/telegram/connect")
async def connect_telegram(payload: TelegramConnectRequest) -> dict[str, Any]:
    runtime = telegram_runtime()
    token = payload.bot_token.strip() or str(runtime["bot_token"] or "")
    if not token:
        raise AppError("Paste the Telegram bot token once to start automatic setup.")
    try:
        proxy_url = (
            ""
            if payload.clear_proxy
            else validate_proxy_url(payload.proxy_url)
            if payload.proxy_url.strip()
            else str(runtime.get("proxy_url") or "")
        )
    except ExternalServiceError as error:
        raise AppError(error.message) from error
    bot = await test_connection(token, proxy_url)
    if payload.bot_token.strip():
        save_telegram_token(
            token,
            proxy_url=proxy_url,
            clear_proxy=payload.clear_proxy,
        )
    elif payload.clear_proxy or payload.proxy_url.strip():
        update_telegram_proxy(proxy_url, clear=payload.clear_proxy)
    await delete_webhook(token, proxy_url)
    bot_name = str(bot["name"])
    bot_username = bot_name.removeprefix("@")
    bot_url = f"https://t.me/{bot_username}" if bot_username else "https://t.me/BotFather"
    if not payload.bot_token.strip() and runtime["chat_id"]:
        existing_chat = await resolve_chat(token, str(runtime["chat_id"]), proxy_url)
        complete_telegram_connection(
            str(existing_chat["chatId"]),
            int(runtime["last_update_id"]),
        )
        await telegram_poller.refresh()
        return {
            "ok": True,
            "connected": True,
            "message": f"Telegram approvals connected to {existing_chat['chatLabel']}.",
            "bot": bot,
            "botUrl": bot_url,
            "chat": {
                "label": existing_chat["chatLabel"],
                "type": existing_chat["chatType"],
            },
            "state": state_response(),
        }
    discovered = await discover_recent_chat(token, proxy_url)
    if discovered is None:
        return {
            "ok": True,
            "connected": False,
            "message": f"{bot_name} is verified. Press Start in Telegram; Socium is waiting.",
            "bot": bot,
            "botUrl": bot_url,
            "state": state_response(),
        }
    complete_telegram_connection(
        str(discovered["chatId"]),
        int(discovered["updateId"]),
    )
    await telegram_poller.refresh()
    return {
        "ok": True,
        "connected": True,
        "message": f"Telegram approvals connected to {discovered['chatLabel']}.",
        "bot": bot,
        "botUrl": bot_url,
        "chat": {
            "label": discovered["chatLabel"],
            "type": discovered["chatType"],
        },
        "state": state_response(),
    }


@app.put("/api/integrations/telegram/polling")
async def configure_polling(payload: PollingUpdate) -> dict[str, Any]:
    runtime = telegram_runtime()
    if payload.enabled:
        if not runtime["bot_token"] or not runtime["chat_id"]:
            raise AppError("Save and test Telegram before starting local approvals.")
        proxy_url = str(runtime.get("proxy_url") or "")
        await test_connection(str(runtime["bot_token"]), proxy_url)
        await delete_webhook(str(runtime["bot_token"]), proxy_url)
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
    result = await generate_content_draft(
        payload.model_dump(),
        approval_wake=lambda: (telegram_poller.wake(), slack_listener.wake()),
    )
    notifications = list(result["notifications"])
    notification = next(
        (item for item in notifications if item.get("channel") == "telegram"),
        None,
    )
    return {
        "ok": True,
        "post": result["post"],
        "notification": notification,
        "notifications": notifications,
        "state": state_response(),
    }


@app.get("/api/posts/generations")
def content_generations(limit: int = 30) -> dict[str, Any]:
    return {"ok": True, "items": list_content_generations(max(1, min(limit, 100)))}


@app.post("/api/posts/generations", status_code=202)
def queue_content_generation(payload: GeneratePostRequest) -> dict[str, Any]:
    provider = provider_runtime()
    if not provider["base_url"] or not provider["model"]:
        raise AppError("Connect an AI provider and select a model first.")
    job = schedule_content_generation(payload, provider)
    local_scheduler.wake()
    return {"ok": True, "job": job}


@app.get("/api/posts/generations/{job_id}")
def content_generation(job_id: str) -> dict[str, Any]:
    job = get_content_generation(job_id)
    response: dict[str, Any] = {"ok": True, "job": job}
    if job["status"] == "completed" and job["resultRef"]:
        state = state_response()
        response["post"] = next(
            (item for item in state["posts"] if item["id"] == job["resultRef"]),
            None,
        )
        response["state"] = state
    return response


@app.post("/api/posts/generations/{job_id}/cancel")
def cancel_queued_content_generation(job_id: str) -> dict[str, Any]:
    return {"ok": True, "job": cancel_content_generation(job_id)}


@app.patch("/api/posts/{post_id}")
def update_post(post_id: str, payload: EditPostRequest) -> dict[str, Any]:
    edit_post(post_id, payload)
    telegram_poller.wake()
    slack_listener.wake()
    return {"ok": True, "state": state_response()}


@app.post("/api/posts/{post_id}/decision")
def post_decision(post_id: str, payload: DecisionRequest) -> dict[str, Any]:
    decide_post(post_id, payload.revision, payload.decision)
    local_scheduler.wake()
    telegram_poller.wake()
    slack_listener.wake()
    return {"ok": True, "state": state_response()}


@app.post("/api/posts/{post_id}/regenerate")
async def regenerate_post(post_id: str, payload: RevisionRequest) -> dict[str, Any]:
    post = await regenerate_post_revision(post_id, payload.revision)
    telegram_poller.wake()
    slack_listener.wake()
    return {
        "ok": True,
        "post": post,
        "message": f"Revision {payload.revision} regenerated as revision {post['revision']}.",
        "state": state_response(),
    }


@app.post("/api/posts/{post_id}/regenerate-image")
async def regenerate_post_image(post_id: str, payload: RevisionRequest) -> dict[str, Any]:
    post = await regenerate_image_revision(post_id, payload.revision)
    telegram_poller.wake()
    slack_listener.wake()
    return {
        "ok": True,
        "post": post,
        "message": f"Image regenerated as revision {post['revision']}.",
        "state": state_response(),
    }


@app.post("/api/approval-actions/{action_id}/edit/ack")
def acknowledge_edit_request(action_id: str) -> dict[str, Any]:
    acknowledge_remote_edit(action_id)
    return {"ok": True}


@app.post("/api/posts/{post_id}/approvals/slack")
async def request_slack_approval(post_id: str, payload: ApprovalRequest) -> dict[str, Any]:
    post = post_for_approval(post_id, payload.revision)
    approval = create_approval_action(post_id, payload.revision, "slack")
    try:
        delivery = await send_saved_slack_approval(post, approval["id"])
        record_approval_sent(approval["id"], delivery["messageTs"])
        slack_listener.wake()
    except AppError as error:
        fail_approval_delivery(approval["id"], error.message)
        raise
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


@app.post("/api/jobs/{job_id}/recover")
async def job_recover(job_id: str, payload: JobRecoveryRequest) -> dict[str, Any]:
    job = recover_missed_job(job_id, payload)
    local_scheduler.wake()
    messages = {
        "run_now": "Missed publish confirmed to run now.",
        "reschedule": "Missed publish rescheduled.",
        "skip": "Missed publish skipped; nothing was sent.",
    }
    return {"ok": True, "job": job, "message": messages[payload.decision], "state": state_response()}


@app.put("/api/scheduler")
async def scheduler_update(payload: SchedulerUpdate) -> dict[str, Any]:
    set_scheduler_paused(payload.paused)
    local_scheduler.set_paused_state(payload.paused)
    return {
        "ok": True,
        "message": "Local scheduler paused." if payload.paused else "Local scheduler resumed.",
        "state": state_response(),
    }


@app.post("/api/automations")
async def automation_create(payload: AutomationRuleUpsert) -> dict[str, Any]:
    automation = create_automation(payload)
    local_scheduler.wake()
    return {"ok": True, "automation": automation, "state": state_response()}


@app.put("/api/automations/{automation_id}")
async def automation_update(automation_id: str, payload: AutomationRuleUpsert) -> dict[str, Any]:
    automation = update_automation(automation_id, payload)
    local_scheduler.wake()
    return {"ok": True, "automation": automation, "state": state_response()}


@app.post("/api/automations/{automation_id}/duplicate")
async def automation_duplicate(automation_id: str) -> dict[str, Any]:
    automation = duplicate_automation(automation_id)
    local_scheduler.wake()
    return {"ok": True, "automation": automation, "state": state_response()}


@app.delete("/api/automations/{automation_id}")
async def automation_delete(automation_id: str) -> dict[str, Any]:
    delete_automation(automation_id)
    local_scheduler.wake()
    return {"ok": True, "state": state_response()}


@app.get("/api/connectors")
def get_connectors() -> dict[str, Any]:
    state = public_connector_state(slack_listener.statuses())
    state["oneClickConfigured"] = oauth_broker.configured()
    return state


@app.post("/api/connectors/oauth/{provider}/start")
async def start_oauth_connector(provider: str) -> dict[str, Any]:
    if provider not in {"slack", "linkedin"}:
        raise AppError("This connector does not support one-click OAuth.", 404)
    connection = await oauth_broker.start(provider)  # type: ignore[arg-type]
    return {"ok": True, "connection": connection}


@app.get("/api/connectors/oauth/sessions/{session_id}")
async def oauth_connector_status(session_id: str) -> dict[str, Any]:
    return {"ok": True, "connection": await oauth_broker.status(session_id), "state": state_response()}


@app.get("/oauth/callback", response_class=HTMLResponse)
async def oauth_callback(request: Request) -> HTMLResponse:
    query = request.query_params
    session = await oauth_broker.complete(
        str(query.get("provider") or ""),
        str(query.get("state") or ""),
        str(query.get("code") or ""),
        str(query.get("error") or ""),
    )
    slack_listener.wake()
    return HTMLResponse(callback_html(session), headers={"cache-control": "no-store"})


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
async def remove_connector(account_id: str) -> dict[str, Any]:
    runtime = connector_runtime(account_id)
    if runtime["adapter_id"] == "slack" and runtime["config"].get("transport") == "broker-relay":
        await oauth_broker.disconnect_slack(str(runtime["secrets"].get("relay_token") or ""))
    delete_connector(account_id)
    slack_listener.wake()
    return {"ok": True, "state": state_response()}
