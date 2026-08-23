from __future__ import annotations

import hashlib
import os
import re
import warnings
from io import BytesIO
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.database import read_session, write_session
from app.errors import AppError
from app.models import MediaAsset, MediaGeneration
from app.schemas import MediaAssetUpdate
from app.store import append_audit, utc_now

MAX_MEDIA_BYTES = 10 * 1024 * 1024
MAX_MEDIA_PIXELS = 40_000_000
MAX_MEDIA_DIMENSION = 12_000
PREVIEW_BOUND = (640, 640)
TRANSFORM_PRESETS: dict[str, tuple[int, int]] = {
    "square": (1080, 1080),
    "portrait": (1080, 1350),
    "landscape": (1200, 628),
}
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._ -]+")
_FORMAT_DETAILS = {
    "JPEG": ("image/jpeg", ".jpg"),
    "PNG": ("image/png", ".png"),
    "WEBP": ("image/webp", ".webp"),
}

Image.MAX_IMAGE_PIXELS = MAX_MEDIA_PIXELS


def _media_directory() -> Path:
    directory = get_settings().data_dir / "media"
    directory.mkdir(parents=True, exist_ok=True)
    return directory.resolve()


def _safe_path(storage_name: str) -> Path:
    directory = _media_directory()
    path = (directory / storage_name).resolve()
    if path.parent != directory:
        raise AppError("Stored media path is invalid.", 500)
    return path


def _clean_original_name(value: str | None) -> str:
    name = Path(value or "upload").name
    cleaned = _SAFE_NAME.sub("-", name).strip(" .-")[:255]
    return cleaned or "upload"


def _inspect_image(data: bytes) -> tuple[Image.Image, str, str]:
    if not data:
        raise AppError("Choose an image to upload.")
    if len(data) > MAX_MEDIA_BYTES:
        raise AppError("Images must be 10 MB or smaller.", 413)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as candidate:
                image_format = str(candidate.format or "").upper()
                candidate.verify()
            if image_format not in _FORMAT_DETAILS:
                raise AppError("Only JPEG, PNG, and WebP images are supported.")
            with Image.open(BytesIO(data)) as decoded:
                decoded.load()
                image = ImageOps.exif_transpose(decoded).copy()
    except AppError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise AppError("Image dimensions are too large.", 413) from error
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as error:
        raise AppError("The image data is not a valid JPEG, PNG, or WebP image.") from error

    width, height = image.size
    if width < 1 or height < 1 or width > MAX_MEDIA_DIMENSION or height > MAX_MEDIA_DIMENSION:
        raise AppError("Image dimensions must be between 1 and 12,000 pixels.", 413)
    if width * height > MAX_MEDIA_PIXELS:
        raise AppError("Images may contain at most 40 megapixels.", 413)
    mime_type, suffix = _FORMAT_DETAILS[image_format]
    return image, mime_type, suffix


def _write_atomic(path: Path, data: bytes) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_bytes(data)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _preview_bytes(image: Image.Image) -> bytes:
    preview = image.copy()
    preview.thumbnail(PREVIEW_BOUND, Image.Resampling.LANCZOS)
    output = BytesIO()
    preview.save(output, format="WEBP", quality=82, method=4)
    return output.getvalue()


def _asset_dict(asset: MediaAsset) -> dict[str, Any]:
    return {
        "id": asset.id,
        "originalName": asset.original_name,
        "mimeType": asset.mime_type,
        "byteSize": asset.byte_size,
        "width": asset.width,
        "height": asset.height,
        "sha256": asset.sha256,
        "source": asset.source,
        "sourceAssetId": asset.source_asset_id,
        "publicSourceUrl": asset.public_source_url,
        "altText": asset.alt_text,
        "generationPrompt": asset.generation_prompt,
        "generationNegativePrompt": asset.generation_negative_prompt,
        "generationProvider": asset.generation_provider,
        "generationModel": asset.generation_model,
        "generationParameters": dict(asset.generation_parameters or {}),
        "contentUrl": f"/api/media/{asset.id}/content",
        "previewUrl": f"/api/media/{asset.id}/preview",
        "instagramReady": bool(asset.public_source_url),
        "createdAt": asset.created_at,
        "updatedAt": asset.updated_at,
    }


def list_media_assets() -> dict[str, Any]:
    with read_session() as session:
        assets = list(session.scalars(select(MediaAsset).order_by(MediaAsset.created_at.desc())).all())
        return {
            "items": [_asset_dict(asset) for asset in assets],
            "total": len(assets),
            "maxUploadBytes": MAX_MEDIA_BYTES,
            "storagePolicy": "local-only",
        }


def _asset_by_id(asset_id: str) -> MediaAsset:
    with read_session() as session:
        asset = session.get(MediaAsset, asset_id)
        if asset is None:
            raise AppError("Media asset not found.", 404)
        session.expunge(asset)
        return asset


def media_asset_path(asset_id: str, variant: Literal["content", "preview"]) -> tuple[Path, str]:
    asset = _asset_by_id(asset_id)
    name = asset.storage_name if variant == "content" else asset.preview_name
    path = _safe_path(name)
    if not path.is_file():
        raise AppError("The media file is missing from local storage.", 404)
    mime_type = asset.mime_type if variant == "content" else "image/webp"
    return path, mime_type


def _save_asset(
    *,
    data: bytes,
    image: Image.Image,
    mime_type: str,
    suffix: str,
    original_name: str,
    source: str,
    source_asset_id: str | None = None,
    alt_text: str = "",
    generation_prompt: str | None = None,
    generation_negative_prompt: str | None = None,
    generation_provider: str | None = None,
    generation_model: str | None = None,
    generation_parameters: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], bool]:
    digest = hashlib.sha256(data).hexdigest()
    with write_session() as session:
        existing = session.scalar(select(MediaAsset).where(MediaAsset.sha256 == digest))
        if existing is not None:
            if alt_text and not existing.alt_text:
                existing.alt_text = alt_text
                existing.updated_at = utc_now()
                session.flush()
            return _asset_dict(existing), True

    asset_id = str(uuid4())
    storage_name = f"{asset_id}{suffix}"
    preview_name = f"{asset_id}.preview.webp"
    storage_path = _safe_path(storage_name)
    preview_path = _safe_path(preview_name)
    _write_atomic(storage_path, data)
    try:
        _write_atomic(preview_path, _preview_bytes(image))
        now = utc_now()
        with write_session() as session:
            asset = MediaAsset(
                id=asset_id,
                original_name=original_name,
                mime_type=mime_type,
                byte_size=len(data),
                width=image.width,
                height=image.height,
                sha256=digest,
                storage_name=storage_name,
                preview_name=preview_name,
                source=source,
                source_asset_id=source_asset_id,
                public_source_url=None,
                alt_text=alt_text,
                generation_prompt=generation_prompt,
                generation_negative_prompt=generation_negative_prompt,
                generation_provider=generation_provider,
                generation_model=generation_model,
                generation_parameters=generation_parameters,
                created_at=now,
                updated_at=now,
            )
            session.add(asset)
            append_audit(
                session,
                action=(
                    "media.created"
                    if source == "upload"
                    else "media.generated"
                    if source == "ai-generated"
                    else "media.transformed"
                ),
                entity_type="media",
                entity_id=asset_id,
                summary=(
                    f"Stored local media asset {original_name}."
                    if source == "upload"
                    else f"Generated local media with {generation_provider}."
                    if source == "ai-generated"
                    else f"Created {source} transform from media asset {source_asset_id}."
                ),
            )
            session.flush()
            result = _asset_dict(asset)
    except (Exception, IntegrityError):
        storage_path.unlink(missing_ok=True)
        preview_path.unlink(missing_ok=True)
        raise
    return result, False


def create_media_asset(data: bytes, filename: str | None) -> dict[str, Any]:
    image, mime_type, suffix = _inspect_image(data)
    asset, deduplicated = _save_asset(
        data=data,
        image=image,
        mime_type=mime_type,
        suffix=suffix,
        original_name=_clean_original_name(filename),
        source="upload",
    )
    return {"asset": asset, "deduplicated": deduplicated}


def create_generated_media_asset(
    data: bytes,
    *,
    prompt: str,
    negative_prompt: str,
    alt_text: str = "",
    provider_kind: str,
    model: str,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    image, mime_type, suffix = _inspect_image(data)
    asset, deduplicated = _save_asset(
        data=data,
        image=image,
        mime_type=mime_type,
        suffix=suffix,
        original_name=f"ai-image-{utc_now().replace(':', '-').replace('Z', '')}{suffix}",
        source="ai-generated",
        alt_text=alt_text,
        generation_prompt=prompt,
        generation_negative_prompt=negative_prompt or None,
        generation_provider=provider_kind,
        generation_model=model,
        generation_parameters=parameters,
    )
    with write_session() as session:
        session.add(
            MediaGeneration(
                id=str(uuid4()),
                asset_id=str(asset["id"]),
                prompt=prompt,
                negative_prompt=negative_prompt,
                provider_kind=provider_kind,
                model=model,
                parameters=parameters,
                created_at=utc_now(),
            )
        )
        if deduplicated:
            append_audit(
                session,
                action="media.generation_reused",
                entity_type="media",
                entity_id=str(asset["id"]),
                summary="A generated image matched an existing local asset and was reused.",
            )
    return {"asset": asset, "deduplicated": deduplicated}


def update_media_asset(asset_id: str, payload: MediaAssetUpdate) -> dict[str, Any]:
    with write_session() as session:
        asset = session.get(MediaAsset, asset_id)
        if asset is None:
            raise AppError("Media asset not found.", 404)
        asset.alt_text = payload.alt_text
        asset.public_source_url = payload.public_source_url
        asset.updated_at = utc_now()
        append_audit(
            session,
            action="media.updated",
            entity_type="media",
            entity_id=asset_id,
            summary=f"Updated media metadata for {asset.original_name}.",
        )
        session.flush()
        return _asset_dict(asset)


def transform_media_asset(asset_id: str, preset: str) -> dict[str, Any]:
    if preset not in TRANSFORM_PRESETS:
        raise AppError("Unknown media transform preset.")
    source_asset = _asset_by_id(asset_id)
    source_path = _safe_path(source_asset.storage_name)
    if not source_path.is_file():
        raise AppError("The source media file is missing from local storage.", 404)
    try:
        with Image.open(source_path) as opened:
            opened.load()
            source_image = ImageOps.exif_transpose(opened)
            transformed = ImageOps.fit(
                source_image,
                TRANSFORM_PRESETS[preset],
                method=Image.Resampling.LANCZOS,
            )
            output = BytesIO()
            transformed.save(output, format="WEBP", quality=88, method=4)
            data = output.getvalue()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as error:
        raise AppError("The source media file could not be transformed.") from error

    stem = Path(source_asset.original_name).stem[:180] or "asset"
    asset, deduplicated = _save_asset(
        data=data,
        image=transformed,
        mime_type="image/webp",
        suffix=".webp",
        original_name=f"{stem}-{preset}.webp",
        source=f"transform:{preset}",
        source_asset_id=source_asset.id,
    )
    return {"asset": asset, "deduplicated": deduplicated}


def delete_media_asset(asset_id: str) -> dict[str, str]:
    asset = _asset_by_id(asset_id)
    with write_session() as session:
        stored = session.get(MediaAsset, asset_id)
        if stored is None:
            raise AppError("Media asset not found.", 404)
        session.delete(stored)
        append_audit(
            session,
            action="media.deleted",
            entity_type="media",
            entity_id=asset_id,
            summary=f"Deleted local media asset {asset.original_name}.",
        )
    _safe_path(asset.storage_name).unlink(missing_ok=True)
    _safe_path(asset.preview_name).unlink(missing_ok=True)
    return {"id": asset_id, "message": "Media asset deleted from this computer."}
