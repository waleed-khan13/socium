from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class AppMetadata(Base):
    __tablename__ = "app_metadata"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)


class Workspace(Base):
    __tablename__ = "workspace"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    business_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    timezone: Mapped[str] = mapped_column(String(80), nullable=False, default="Asia/Karachi")
    website: Mapped[str] = mapped_column(String(2048), nullable=False, default="")
    industry: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    products_services: Mapped[str] = mapped_column(Text, nullable=False, default="")
    target_audience: Mapped[str] = mapped_column(Text, nullable=False, default="")
    location: Mapped[str] = mapped_column(String(240), nullable=False, default="")
    goals: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    call_to_action: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    language: Mapped[str] = mapped_column(String(80), nullable=False, default="English")
    tone: Mapped[str] = mapped_column(String(240), nullable=False, default="Clear and confident")
    content_pillars: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    restricted_claims: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    branded_hashtags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    logo_media_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reference_media_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    primary_color: Mapped[str] = mapped_column(String(7), nullable=False, default="#f59e0b")
    secondary_color: Mapped[str] = mapped_column(String(7), nullable=False, default="#18181b")
    accent_color: Mapped[str] = mapped_column(String(7), nullable=False, default="#10b981")
    heading_font: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    body_font: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    visual_style: Mapped[str] = mapped_column(Text, nullable=False, default="")
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    confirmed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    updated_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class ProviderSettings(Base):
    __tablename__ = "provider_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    kind: Mapped[str] = mapped_column(String(40), nullable=False, default="ollama")
    base_url: Mapped[str] = mapped_column(String(2048), nullable=False, default="http://127.0.0.1:11434")
    model: Mapped[str] = mapped_column(String(180), nullable=False, default="")
    api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class ImageProviderSettings(Base):
    __tablename__ = "image_provider_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    kind: Mapped[str] = mapped_column(String(40), nullable=False, default="automatic1111")
    base_url: Mapped[str] = mapped_column(String(2048), nullable=False, default="http://127.0.0.1:7860")
    model: Mapped[str] = mapped_column(String(180), nullable=False, default="")
    api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    workflow_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class TelegramSettings(Base):
    __tablename__ = "telegram_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    chat_id: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    bot_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    proxy_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    polling_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_update_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class ConnectorAccount(Base):
    __tablename__ = "connector_accounts"
    __table_args__ = (UniqueConstraint("adapter_id", "name", name="uq_connector_adapter_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    adapter_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    encrypted_secrets: Mapped[str] = mapped_column(Text, nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="saved", index=True)
    remote_account_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_verified_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str] = mapped_column(String(40), nullable=False)
    tone: Mapped[str] = mapped_column(String(160), nullable=False)
    objective: Mapped[str] = mapped_column(String(500), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    hashtags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    call_to_action: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    image_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    image_negative_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    image_alt_text: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    brand_profile_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    media_asset_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("media_assets.id", ondelete="SET NULL"), nullable=True, index=True
    )
    media_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    rationale: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending", index=True)
    provider_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(180), nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)
    approved_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    published_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    remote_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    remote_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    automation_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("automation_rules.id", ondelete="SET NULL"), nullable=True, index=True
    )
    automation_publish_at: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)


class ApprovalAction(Base):
    __tablename__ = "approval_actions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    post_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    transport: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="created", index=True)
    selected_action: Mapped[str | None] = mapped_column(String(30), nullable=True)
    remote_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    expires_at: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    consumed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class MediaAsset(Base):
    __tablename__ = "media_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(80), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    storage_name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    preview_name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    source: Mapped[str] = mapped_column(String(40), nullable=False, default="upload", index=True)
    source_asset_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    public_source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    alt_text: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    generation_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    generation_negative_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    generation_provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    generation_model: Mapped[str | None] = mapped_column(String(180), nullable=True)
    generation_parameters: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)


class MediaGeneration(Base):
    __tablename__ = "media_generations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    asset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("media_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    negative_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    provider_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(180), nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False, index=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    action: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False, index=True)


class LocalJob(Base):
    __tablename__ = "local_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="queued", index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    run_at: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    locked_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    lease_token: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    lease_expires_at: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    recovery_required_at: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    recovery_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    completed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    progress_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    remote_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    result_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)


class AutomationRule(Base):
    __tablename__ = "automation_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    channel: Mapped[str] = mapped_column(String(40), nullable=False)
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    tone: Mapped[str] = mapped_column(String(160), nullable=False)
    objective: Mapped[str] = mapped_column(String(500), nullable=False)
    timezone: Mapped[str] = mapped_column(String(80), nullable=False)
    days_of_week: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list)
    publish_time: Mapped[str] = mapped_column(String(5), nullable=False)
    approval_channels: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    generate_ahead_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    publish_after_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    next_run_at: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    next_publish_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_run_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    business_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    website: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(80), nullable=True)
    location: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    source_ref: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="new", index=True)
    suppressed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    suppression_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    suppressed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    icp_score: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    icp_reasons: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    icp_profile_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    icp_scored_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    manual_score: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    manual_score_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    manual_score_updated_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    consent_status: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown", index=True)
    legal_basis: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)
    legal_basis_note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    retention_until: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    compliance_reviewed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False, index=True)


class LeadIdentity(Base):
    __tablename__ = "lead_identities"
    __table_args__ = (UniqueConstraint("kind", "value", name="uq_lead_identity_kind_value"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lead_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    value: Mapped[str] = mapped_column(String(512), nullable=False)


class IcpProfile(Base):
    __tablename__ = "icp_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    name: Mapped[str] = mapped_column(String(120), nullable=False, default="Primary ICP")
    target_keywords: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    excluded_keywords: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    target_locations: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    require_website: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    require_contact: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class OutreachDraft(Base):
    __tablename__ = "outreach_drafts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    lead_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    channel: Mapped[str] = mapped_column(String(40), nullable=False, default="email")
    objective: Mapped[str] = mapped_column(String(500), nullable=False)
    tone: Mapped[str] = mapped_column(String(160), nullable=False)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft", index=True)
    provider_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(180), nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)
    approved_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    exported_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class SeoAuditSnapshot(Base):
    __tablename__ = "seo_audit_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    requested_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    final_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    hostname: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    trigger: Mapped[str] = mapped_column(String(40), nullable=False, default="manual", index=True)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    overall_score: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    scores: Mapped[dict[str, int]] = mapped_column(JSON, nullable=False, default=dict)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    checks: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    robots_respected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    user_agent: Mapped[str] = mapped_column(String(255), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
