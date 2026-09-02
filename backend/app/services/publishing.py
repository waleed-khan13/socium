from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.connector_store import primary_connector_runtime
from app.errors import AppError
from app.media_store import media_asset_delivery
from app.services.instagram import publish_instagram_image
from app.services.linkedin import (
    publish_linkedin_member_post,
    publish_linkedin_organization_post,
)
from app.services.meta import publish_facebook_page_post
from app.services.telegram import publish_post as publish_telegram_post
from app.services.wordpress import publish_wordpress_post
from app.store import telegram_runtime


@dataclass(frozen=True, slots=True)
class PublishTarget:
    channel: str
    name: str
    runtime: dict[str, Any]


@dataclass(frozen=True, slots=True)
class PublishResult:
    remote_id: str
    remote_url: str | None = None


def resolve_publish_target(channel: str) -> PublishTarget:
    if channel == "telegram":
        runtime = telegram_runtime()
        if not runtime["bot_token"] or not runtime["chat_id"]:
            raise AppError("Connect Telegram before publishing.")
        return PublishTarget(channel=channel, name="Telegram", runtime=runtime)
    if channel == "blog":
        runtime = primary_connector_runtime("wordpress", verified_only=True)
        return PublishTarget(channel=channel, name="WordPress", runtime=runtime)
    if channel == "facebook":
        runtime = primary_connector_runtime("meta", verified_only=True)
        return PublishTarget(channel=channel, name="Meta Pages", runtime=runtime)
    if channel == "instagram":
        runtime = primary_connector_runtime("instagram", verified_only=True)
        return PublishTarget(channel=channel, name="Instagram", runtime=runtime)
    if channel == "linkedin":
        runtime = primary_connector_runtime("linkedin", verified_only=True)
        return PublishTarget(channel=channel, name="LinkedIn", runtime=runtime)
    if channel == "linkedin-company":
        runtime = primary_connector_runtime("linkedin-organization", verified_only=True)
        return PublishTarget(channel=channel, name="LinkedIn Company Page", runtime=runtime)
    raise AppError(f"{channel} publisher is not installed yet.")


async def publish_to_target(target: PublishTarget, post: dict[str, Any]) -> PublishResult:
    media_asset_id = str(post.get("mediaAssetId") or "")
    media = media_asset_delivery(media_asset_id) if media_asset_id else None
    if target.channel == "telegram":
        remote_id = await publish_telegram_post(
            str(target.runtime["bot_token"]),
            str(target.runtime["chat_id"]),
            post,
            str(target.runtime.get("proxy_url") or ""),
        )
        return PublishResult(remote_id=remote_id)
    if target.channel == "blog":
        result = await publish_wordpress_post(
            str(target.runtime["config"].get("site_url") or ""),
            str(target.runtime["secrets"].get("username") or ""),
            str(target.runtime["secrets"].get("application_password") or ""),
            post,
        )
        return PublishResult(remote_id=result.remote_id, remote_url=result.remote_url)
    if target.channel == "facebook":
        result = await publish_facebook_page_post(
            str(target.runtime["config"].get("page_id") or ""),
            str(target.runtime["config"].get("api_version") or "v25.0"),
            str(target.runtime["secrets"].get("page_access_token") or ""),
            post,
        )
        return PublishResult(remote_id=result.remote_id, remote_url=result.remote_url)
    if target.channel == "instagram":
        result = await publish_instagram_image(
            str(target.runtime["config"].get("user_id") or ""),
            str(target.runtime["config"].get("api_version") or "v25.0"),
            str(target.runtime["secrets"].get("access_token") or ""),
            post,
        )
        return PublishResult(remote_id=result.remote_id, remote_url=result.remote_url)
    if target.channel == "linkedin":
        result = await publish_linkedin_member_post(
            str(target.runtime["config"].get("person_id") or ""),
            str(target.runtime["config"].get("api_version") or "202607"),
            str(target.runtime["secrets"].get("access_token") or ""),
            post,
            media,
        )
        return PublishResult(remote_id=result.remote_id, remote_url=result.remote_url)
    if target.channel == "linkedin-company":
        result = await publish_linkedin_organization_post(
            str(target.runtime["config"].get("organization_id") or ""),
            str(target.runtime["config"].get("api_version") or "202607"),
            str(target.runtime["secrets"].get("access_token") or ""),
            post,
            media,
        )
        return PublishResult(remote_id=result.remote_id, remote_url=result.remote_url)
    raise AppError(f"{target.channel} publisher is not installed yet.")
