from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
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


class ProviderUpdate(ApiModel):
    kind: Literal[
        "ollama",
        "openai",
        "gemini",
        "anthropic",
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
