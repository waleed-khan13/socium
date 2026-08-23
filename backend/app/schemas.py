from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import Any, Literal, Self
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator
from pydantic.alias_generators import to_camel

from app.errors import ExternalServiceError
from app.services.instagram import validate_instagram_media_url


def _validate_post_media_url(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    try:
        return validate_instagram_media_url(value)
    except ExternalServiceError as error:
        raise ValueError(error.message) from error


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, str_strip_whitespace=True)


class WorkspaceUpdate(ApiModel):
    name: str = Field(min_length=1, max_length=80)
    business_name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2_000)
    timezone: str = Field(default="Asia/Karachi", max_length=80)


class BrandProfileUpdate(ApiModel):
    name: str = Field(min_length=1, max_length=80)
    business_name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=2_000)
    timezone: str = Field(default="Asia/Karachi", min_length=1, max_length=80)
    website: str = Field(default="", max_length=2_048)
    industry: str = Field(default="", max_length=160)
    products_services: str = Field(min_length=1, max_length=4_000)
    target_audience: str = Field(min_length=1, max_length=3_000)
    location: str = Field(default="", max_length=240)
    goals: list[str] = Field(min_length=1, max_length=12)
    call_to_action: str = Field(min_length=1, max_length=500)
    language: str = Field(min_length=1, max_length=80)
    tone: str = Field(min_length=1, max_length=240)
    content_pillars: list[str] = Field(min_length=1, max_length=12)
    restricted_claims: list[str] = Field(default_factory=list, max_length=20)
    branded_hashtags: list[str] = Field(default_factory=list, max_length=20)
    logo_media_id: str | None = Field(default=None, max_length=36, pattern=r"^[0-9a-fA-F-]{36}$")
    reference_media_ids: list[str] = Field(default_factory=list, max_length=12)
    primary_color: str = Field(default="#f59e0b", pattern=r"^#[0-9a-fA-F]{6}$")
    secondary_color: str = Field(default="#18181b", pattern=r"^#[0-9a-fA-F]{6}$")
    accent_color: str = Field(default="#10b981", pattern=r"^#[0-9a-fA-F]{6}$")
    visual_style: str = Field(default="", max_length=2_000)

    @field_validator("website")
    @classmethod
    def validate_website(cls, value: str) -> str:
        if not value:
            return ""
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Website must be a valid http or https URL.")
        if parsed.username or parsed.password:
            raise ValueError("Website URL must not contain credentials.")
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), parsed.query, ""))

    @field_validator(
        "goals",
        "content_pillars",
        "restricted_claims",
        "branded_hashtags",
        "reference_media_ids",
    )
    @classmethod
    def normalize_lists(cls, values: list[str], info: ValidationInfo) -> list[str]:
        maximum = 36 if info.field_name == "reference_media_ids" else 240
        cleaned: list[str] = []
        seen: set[str] = set()
        for raw in values:
            value = raw.strip()
            if info.field_name == "branded_hashtags" and value:
                value = f"#{value.lstrip('#')}"
                if not value[1:].replace("_", "").isalnum():
                    raise ValueError("Branded hashtags may contain only letters, numbers, or underscores.")
            if info.field_name == "reference_media_ids":
                try:
                    value = str(UUID(value))
                except ValueError as error:
                    raise ValueError("Reference media contains an invalid asset ID.") from error
            if not value or len(value) > maximum:
                raise ValueError(f"{info.field_name.replace('_', ' ').title()} contains an invalid item.")
            identity = value.casefold()
            if identity not in seen:
                cleaned.append(value)
                seen.add(identity)
        return cleaned


class OnboardingUpdate(ApiModel):
    action: Literal["start", "set-step", "confirm-storage", "dismiss", "complete", "reset"]
    step: Literal["welcome", "storage", "ai", "brand", "finish"] | None = None
    acknowledge_warnings: bool = False

    @model_validator(mode="after")
    def require_step_for_navigation(self) -> Self:
        if self.action == "set-step" and self.step is None:
            raise ValueError("Choose an onboarding step.")
        return self


class ProviderUpdate(ApiModel):
    kind: Literal[
        "ollama",
        "openai",
        "gemini",
        "anthropic",
        "anthropic-compatible",
        "openrouter",
        "nvidia",
        "openai-compatible",
    ]
    base_url: str = Field(min_length=1, max_length=2_048)
    model: str = Field(default="", max_length=180)
    api_key: str = Field(default="", max_length=2_000)


class ImageProviderUpdate(ApiModel):
    kind: Literal["openai-images", "automatic1111", "comfyui"]
    base_url: str = Field(min_length=1, max_length=2_048)
    model: str = Field(default="", max_length=180)
    api_key: str = Field(default="", max_length=2_000)
    workflow_json: str = Field(default="", max_length=200_000)

    @model_validator(mode="after")
    def require_hosted_model(self) -> Self:
        if self.kind == "openai-images" and not self.model:
            raise ValueError("Choose an image model for an OpenAI-compatible provider.")
        return self

    @field_validator("workflow_json")
    @classmethod
    def validate_workflow_json(cls, value: str) -> str:
        if not value:
            return ""
        try:
            workflow = json.loads(value)
        except json.JSONDecodeError as error:
            raise ValueError("ComfyUI workflow must be valid JSON exported in API format.") from error
        if not isinstance(workflow, dict) or not workflow:
            raise ValueError("ComfyUI workflow must be a non-empty JSON object.")
        if len(workflow) > 1_000:
            raise ValueError("ComfyUI workflow contains too many nodes.")
        return json.dumps(workflow, separators=(",", ":"), ensure_ascii=False)


class ImageGenerateRequest(ApiModel):
    prompt: str = Field(min_length=3, max_length=4_000)
    negative_prompt: str = Field(default="", max_length=2_000)
    alt_text: str = Field(default="", max_length=500)
    preset: Literal["square", "portrait", "landscape"] = "square"
    quality: Literal["low", "medium", "high", "auto"] = "auto"
    steps: int = Field(default=28, ge=1, le=80)
    guidance_scale: float = Field(default=7, ge=1, le=20)
    seed: int = Field(default=-1, ge=-1, le=2_147_483_647)


class TelegramUpdate(ApiModel):
    chat_id: str = Field(min_length=1, max_length=160)
    bot_token: str = Field(default="", max_length=2_000)


class PollingUpdate(ApiModel):
    enabled: bool


class GeneratePostRequest(ApiModel):
    model_config = ConfigDict(extra="forbid")

    topic: str = Field(min_length=1, max_length=1_000)
    channel: Literal[
        "linkedin",
        "linkedin-company",
        "instagram",
        "facebook",
        "x",
        "telegram",
        "blog",
    ]
    tone: str = Field(default="Clear and confident", max_length=160)
    objective: str = Field(default="Build useful awareness", max_length=500)
    media_url: str | None = Field(default=None, max_length=2_048)
    notify_telegram: bool = True
    notify_slack: bool = False

    _validate_media_url = field_validator("media_url")(_validate_post_media_url)

    @model_validator(mode="after")
    def require_instagram_media(self) -> Self:
        if self.channel == "instagram" and not self.media_url:
            raise ValueError("Instagram drafts require a public image URL.")
        return self


class EditPostRequest(ApiModel):
    title: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=12_000)
    hashtags: list[str] = Field(default_factory=list, max_length=20)
    call_to_action: str | None = Field(default=None, max_length=500)
    image_prompt: str | None = Field(default=None, max_length=4_000)
    image_negative_prompt: str | None = Field(default=None, max_length=2_000)
    image_alt_text: str | None = Field(default=None, max_length=500)
    media_url: str | None = Field(default=None, max_length=2_048)

    _validate_media_url = field_validator("media_url")(_validate_post_media_url)

    @field_validator("hashtags")
    @classmethod
    def validate_hashtags(cls, hashtags: list[str]) -> list[str]:
        cleaned = [tag.strip()[:80] for tag in hashtags if tag.strip()]
        return cleaned[:20]


class DecisionRequest(ApiModel):
    decision: Literal["approve", "reject"]
    revision: int = Field(ge=1)


class ApprovalRequest(ApiModel):
    revision: int = Field(ge=1)


class PublishRequest(ApiModel):
    revision: int = Field(ge=1)


class SchedulePostRequest(ApiModel):
    revision: int = Field(ge=1)
    run_at: datetime

    @field_validator("run_at")
    @classmethod
    def require_timezone(cls, run_at: datetime) -> datetime:
        if run_at.tzinfo is None or run_at.utcoffset() is None:
            raise ValueError("runAt must include a timezone offset.")
        return run_at.astimezone(UTC)


class SchedulerUpdate(ApiModel):
    paused: bool


class MediaAssetUpdate(ApiModel):
    alt_text: str = Field(default="", max_length=500)
    public_source_url: str | None = Field(default=None, max_length=2_048)

    _validate_public_source_url = field_validator("public_source_url")(_validate_post_media_url)


class MediaTransformRequest(ApiModel):
    preset: Literal["square", "portrait", "landscape"]


class LeadImportRow(ApiModel):
    business_name: str = Field(default="", max_length=200)
    website: str = Field(default="", max_length=2_048)
    email: str = Field(default="", max_length=320)
    phone: str = Field(default="", max_length=80)
    location: str = Field(default="", max_length=500)
    source_ref: str = Field(default="", max_length=2_048)
    notes: str = Field(default="", max_length=4_000)

    @model_validator(mode="after")
    def require_identity(self) -> Self:
        if not any((self.business_name, self.website, self.email, self.phone)):
            raise ValueError("Each lead needs a business name, website, email, or phone number.")
        return self


class LeadImportRequest(ApiModel):
    source: Literal["csv", "linkedin-export", "crm-export", "manual", "website-crawl"] = "csv"
    rows: list[LeadImportRow] = Field(min_length=1, max_length=1_000)


class GooglePlacesSearchRequest(ApiModel):
    query: str = Field(min_length=2, max_length=200)
    page_size: int = Field(default=10, ge=1, le=20)


class WebsiteCrawlRequest(ApiModel):
    url: str = Field(min_length=4, max_length=2_048)


class SeoAuditRequest(ApiModel):
    url: str = Field(min_length=4, max_length=2_048)


class SeoAuditScheduleRequest(ApiModel):
    url: str = Field(min_length=4, max_length=2_048)
    run_at: datetime

    @field_validator("run_at")
    @classmethod
    def require_timezone(cls, run_at: datetime) -> datetime:
        if run_at.tzinfo is None or run_at.utcoffset() is None:
            raise ValueError("runAt must include a timezone offset.")
        return run_at.astimezone(UTC)


class LeadStatusUpdate(ApiModel):
    status: Literal["new", "qualified", "contacted", "archived"]


class LeadSuppressionUpdate(ApiModel):
    reason: str = Field(min_length=1, max_length=500)


class IcpProfileUpdate(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    target_keywords: list[str] = Field(default_factory=list, max_length=30)
    excluded_keywords: list[str] = Field(default_factory=list, max_length=30)
    target_locations: list[str] = Field(default_factory=list, max_length=30)
    require_website: bool = False
    require_contact: bool = False

    @field_validator("target_keywords", "excluded_keywords", "target_locations")
    @classmethod
    def clean_criteria(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for value in values:
            item = value.strip()[:100]
            key = item.casefold()
            if item and key not in seen:
                cleaned.append(item)
                seen.add(key)
        return cleaned

    @model_validator(mode="after")
    def require_target(self) -> Self:
        if not self.target_keywords and not self.target_locations:
            raise ValueError("Add at least one target keyword or target location.")
        return self


class LeadScoreOverrideUpdate(ApiModel):
    score: int = Field(ge=0, le=100)
    reason: str = Field(min_length=3, max_length=500)


class LeadComplianceUpdate(ApiModel):
    consent_status: Literal["unknown", "granted", "not_applicable", "denied", "withdrawn"]
    legal_basis: Literal["consent", "legitimate_interest", "existing_customer", "contract", "other"]
    legal_basis_note: str = Field(min_length=5, max_length=2_000)
    retention_until: date


class OutreachGenerateRequest(ApiModel):
    objective: str = Field(min_length=3, max_length=500)
    tone: str = Field(default="Clear, relevant, and respectful", min_length=2, max_length=160)


class OutreachDraftUpdate(ApiModel):
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=12_000)


class OutreachDecisionRequest(ApiModel):
    decision: Literal["approve", "reject"]
    revision: int = Field(ge=1)


class OutreachExportRequest(ApiModel):
    revision: int = Field(ge=1)


class LeadDeleteRequest(ApiModel):
    reason: str = Field(min_length=5, max_length=500)
    confirmation: Literal["DELETE"]


class ConnectorAccountUpsert(ApiModel):
    adapter_id: str = Field(pattern=r"^[a-z][a-z0-9-]{1,79}$")
    name: str = Field(min_length=1, max_length=120)
    config: dict[str, Any] = Field(default_factory=dict)
    secrets: dict[str, str] = Field(default_factory=dict)
    scopes: list[str] = Field(default_factory=list, max_length=30)
    enabled: bool = True

    @field_validator("config")
    @classmethod
    def validate_config(cls, config: dict[str, Any]) -> dict[str, Any]:
        if len(config) > 30:
            raise ValueError("Connector config has too many fields.")
        return config

    @field_validator("secrets")
    @classmethod
    def validate_secrets(cls, secrets: dict[str, str]) -> dict[str, str]:
        if len(secrets) > 20:
            raise ValueError("Connector secret payload has too many fields.")
        cleaned: dict[str, str] = {}
        for key, value in secrets.items():
            clean_key = key.strip()
            if not clean_key or len(clean_key) > 80 or len(value) > 8_000:
                raise ValueError("Connector secret field is invalid.")
            if value.strip():
                cleaned[clean_key] = value.strip()
        return cleaned

    @field_validator("scopes")
    @classmethod
    def validate_scopes(cls, scopes: list[str]) -> list[str]:
        cleaned = sorted({scope.strip() for scope in scopes if scope.strip()})
        if any(len(scope) > 120 for scope in cleaned):
            raise ValueError("Connector scope is too long.")
        return cleaned


class GeneratedContent(ApiModel):
    title: str
    body: str
    hashtags: list[str] = Field(default_factory=list)
    call_to_action: str = ""
    image_prompt: str = ""
    image_negative_prompt: str = ""
    image_alt_text: str = ""
    rationale: str = ""


class GeneratedOutreach(ApiModel):
    subject: str
    body: str
    rationale: str = ""


class ProviderConnectionResult(ApiModel):
    ok: bool
    message: str
    models: list[str] | None = None
    latency_ms: int | None = None


class ProviderDiscoveryRequest(ApiModel):
    base_url: str = Field(min_length=1, max_length=2_048)
    protocol_hint: Literal["auto", "ollama", "openai-compatible", "anthropic-compatible"] = "auto"
    api_key: str = Field(default="", max_length=2_000)

    @model_validator(mode="after")
    def protect_unknown_credentials(self) -> Self:
        if self.protocol_hint == "auto" and self.api_key:
            raise ValueError("Choose one API protocol before testing with a secret key.")
        return self


class LocalModelPullRequest(ApiModel):
    base_url: str = Field(min_length=1, max_length=2_048)
    model: str = Field(
        min_length=1,
        max_length=180,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]*(?::[A-Za-z0-9][A-Za-z0-9._-]*)?$",
    )
