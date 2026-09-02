from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.errors import AppError
from app.runtime_signals import wake_scheduler
from app.services.content_package import regenerate_post_image
from app.services.provider import generate_content
from app.store import (
    claim_remote_approval_action,
    fail_remote_regeneration,
    finish_image_regeneration,
    finish_post_regeneration,
    post_for_regeneration,
    provider_runtime,
    workspace_runtime,
)

ApprovalChoice = Literal[
    "approve",
    "regenerate",
    "regenerate_post",
    "regenerate_image",
    "edit",
    "skip",
]
ApprovalTransport = Literal["telegram", "slack"]


@dataclass(frozen=True, slots=True)
class ApprovalActionResult:
    message: str
    post: dict[str, Any]
    regenerated: bool = False


async def regenerate_post_revision(
    post_id: str,
    revision: int,
    *,
    source: str = "dashboard",
    approval_action_id: str | None = None,
    claimed_post: dict[str, Any] | None = None,
) -> dict[str, Any]:
    post = claimed_post or post_for_regeneration(post_id, revision)
    provider = provider_runtime()
    if not provider["base_url"] or not provider["model"]:
        raise AppError("Connect and verify an AI provider before regenerating this draft.")
    workspace = workspace_runtime()
    request = {
        "topic": post["topic"],
        "channel": post["channel"],
        "tone": post["tone"],
        "objective": post["objective"],
        "media_url": post.get("mediaUrl"),
    }
    try:
        generated = await generate_content(provider, request, workspace)
        regenerated_content = generated.model_dump()
        regenerated_content.update(
            {
                "image_prompt": post.get("imagePrompt", ""),
                "image_negative_prompt": post.get("imageNegativePrompt", ""),
                "image_alt_text": post.get("imageAltText", ""),
            }
        )
        return finish_post_regeneration(
            post_id,
            revision,
            content=regenerated_content,
            provider=provider,
            brand_profile_version=int(workspace.get("profile_version") or 0),
            source=source,
            approval_action_id=approval_action_id,
        )
    except AppError as error:
        if approval_action_id:
            fail_remote_regeneration(approval_action_id, error.message)
        raise
    except Exception as error:
        message = "Regeneration stopped because the AI provider returned an unexpected failure."
        if approval_action_id:
            fail_remote_regeneration(approval_action_id, message)
        raise AppError(message) from error


async def regenerate_image_revision(
    post_id: str,
    revision: int,
    *,
    source: str = "dashboard",
) -> dict[str, Any]:
    post = post_for_regeneration(post_id, revision)
    media_asset_id = await regenerate_post_image(post)
    return finish_image_regeneration(
        post_id,
        revision,
        media_asset_id=media_asset_id,
        source=source,
    )


async def apply_remote_approval_action(
    action_id: str,
    action: ApprovalChoice,
    source: ApprovalTransport,
) -> ApprovalActionResult:
    post = claim_remote_approval_action(action_id, action, source)
    revision = int(post["revision"])
    approval_replay = bool(post.pop("approvalReplay", False))
    if action == "approve":
        if approval_replay:
            status = str(post.get("status") or "approved")
            if status == "published":
                return ApprovalActionResult(
                    f"Revision {revision} was already approved and published. No duplicate post was created.",
                    post,
                )
            if status == "publishing":
                return ApprovalActionResult(
                    f"Revision {revision} was already approved and is publishing. No second publish was started.",
                    post,
                )
            return ApprovalActionResult(
                f"Revision {revision} was already approved. No duplicate publish job was created.",
                post,
            )
        wake_scheduler()
        return ApprovalActionResult(f"Revision {revision} approved and locked.", post)
    if action == "skip":
        if approval_replay:
            return ApprovalActionResult(
                f"Revision {revision} was already skipped; no additional action was taken.",
                post,
            )
        return ApprovalActionResult(f"Revision {revision} skipped; it will not be published.", post)
    if action == "edit":
        return ApprovalActionResult(
            f"Revision {revision} queued to open in Socium. Save the edit on this computer to create a new revision.",
            post,
        )
    normalized_action = "regenerate_post" if action == "regenerate" else action
    if normalized_action == "regenerate_image":
        try:
            media_asset_id = await regenerate_post_image(post)
            regenerated = finish_image_regeneration(
                str(post["id"]),
                revision,
                media_asset_id=media_asset_id,
                source=source,
                approval_action_id=action_id,
            )
        except AppError as error:
            fail_remote_regeneration(action_id, error.message)
            raise
    else:
        regenerated = await regenerate_post_revision(
            str(post["id"]),
            revision,
            source=source,
            approval_action_id=action_id,
            claimed_post=post,
        )
    regenerated_label = "image" if normalized_action == "regenerate_image" else "post"
    return ApprovalActionResult(
        f"The {regenerated_label} was regenerated as revision {regenerated['revision']}; fresh approval is required.",
        regenerated,
        regenerated=True,
    )
