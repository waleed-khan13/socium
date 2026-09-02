from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.errors import AppError, ExternalServiceError
from app.media_store import create_generated_media_asset
from app.schemas import GeneratedContent, ImageGenerateRequest
from app.services.image_generation import generate_image
from app.services.local_brand_visual import render_local_brand_visual
from app.services.provider import generate_content
from app.store import primary_image_runtime, workspace_runtime


@dataclass(frozen=True, slots=True)
class GeneratedPostPackage:
    content: GeneratedContent
    media_asset_id: str
    image_provider_kind: str
    image_model: str


def image_preset_for_channel(channel: str) -> str:
    if channel == "instagram":
        return "portrait"
    if channel in {"linkedin", "linkedin-company", "facebook", "x", "blog"}:
        return "landscape"
    return "square"


async def _generate_and_store_image(
    image_request: ImageGenerateRequest,
    content: dict[str, Any],
    workspace: dict[str, Any],
) -> tuple[str, str, str]:
    try:
        image_settings = primary_image_runtime()
        generated = await generate_image(image_settings, image_request)
        data = generated.data
        provider_kind = generated.provider_kind
        model = generated.model
        parameters = generated.parameters
    except (AppError, ExternalServiceError) as error:
        data = render_local_brand_visual(content, workspace, image_request.preset)
        provider_kind = "socium-local"
        model = "brand-card-v1"
        parameters = {
            "preset": image_request.preset,
            "fallbackReason": error.message[:500],
            "renderer": "local-brand-card",
        }
    saved = create_generated_media_asset(
        data,
        prompt=image_request.prompt,
        negative_prompt=image_request.negative_prompt,
        alt_text=image_request.alt_text,
        provider_kind=provider_kind,
        model=model,
        parameters=parameters,
    )
    return str(saved["asset"]["id"]), provider_kind, model


async def generate_post_package(
    provider: dict[str, str],
    request: dict[str, Any],
    workspace: dict[str, Any],
) -> GeneratedPostPackage:
    try:
        content = await generate_content(provider, request, workspace)
    except ExternalServiceError as error:
        raise ExternalServiceError(f"Text generation failed: {error.message}") from error
    image_request = ImageGenerateRequest(
        prompt=content.image_prompt,
        negative_prompt=content.image_negative_prompt,
        alt_text=content.image_alt_text,
        preset=image_preset_for_channel(str(request.get("channel") or "")),
        quality="auto",
        steps=28,
        guidance_scale=7,
        seed=-1,
    )
    asset_id, provider_kind, model = await _generate_and_store_image(
        image_request,
        content.model_dump(),
        workspace,
    )
    return GeneratedPostPackage(
        content=content,
        media_asset_id=asset_id,
        image_provider_kind=provider_kind,
        image_model=model,
    )


async def regenerate_post_image(post: dict[str, Any]) -> str:
    image_request = ImageGenerateRequest(
        prompt=str(post.get("imagePrompt") or ""),
        negative_prompt=str(post.get("imageNegativePrompt") or ""),
        alt_text=str(post.get("imageAltText") or ""),
        preset=image_preset_for_channel(str(post.get("channel") or "")),
        quality="auto",
        steps=28,
        guidance_scale=7,
        seed=-1,
    )
    asset_id, _, _ = await _generate_and_store_image(
        image_request,
        post,
        workspace_runtime(),
    )
    return asset_id
