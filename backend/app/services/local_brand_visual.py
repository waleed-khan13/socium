from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageColor, ImageDraw, ImageFont, ImageOps

from app.errors import AppError
from app.media_store import media_asset_path

CARD_SIZES = {
    "square": (1200, 1200),
    "portrait": (1080, 1350),
    "landscape": (1536, 1024),
}


def _color(value: object, fallback: str) -> tuple[int, int, int]:
    try:
        return ImageColor.getrgb(str(value or fallback))
    except ValueError:
        return ImageColor.getrgb(fallback)


def _font(size: int, *, bold: bool = False):  # type: ignore[no-untyped-def]
    names = (
        ("DejaVuSans-Bold.ttf", "Arial Bold.ttf", "arialbd.ttf")
        if bold
        else ("DejaVuSans.ttf", "Arial.ttf", "arial.ttf")
    )
    for name in names:
        try:
            return ImageFont.truetype(name, size=size)
        except OSError:
            continue
    return ImageFont.load_default(size=max(10, size // 3))


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, width: int, lines: int) -> list[str]:  # type: ignore[no-untyped-def]
    words = text.split()
    rendered: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textbbox((0, 0), candidate, font=font)[2] <= width:
            current = candidate
            continue
        if current:
            rendered.append(current)
        current = word
        if len(rendered) == lines:
            break
    if current and len(rendered) < lines:
        rendered.append(current)
    if len(rendered) == lines and len(" ".join(rendered)) < len(text):
        rendered[-1] = rendered[-1].rstrip(" .") + "…"
    return rendered


def _brand_logo(workspace: dict[str, Any], maximum: int) -> Image.Image | None:
    asset_id = str(workspace.get("logo_media_id") or "")
    if not asset_id:
        return None
    try:
        path, _ = media_asset_path(asset_id, "content")
        with Image.open(Path(path)) as opened:
            opened.load()
            logo = ImageOps.exif_transpose(opened).convert("RGBA")
            logo.thumbnail((maximum, maximum), Image.Resampling.LANCZOS)
            return logo.copy()
    except (AppError, OSError, SyntaxError, ValueError):
        return None


def render_local_brand_visual(
    content: dict[str, Any],
    workspace: dict[str, Any],
    preset: str,
) -> bytes:
    width, height = CARD_SIZES.get(preset, CARD_SIZES["square"])
    colors = list(workspace.get("brand_colors") or [])
    primary = _color(colors[0] if colors else None, "#006efe")
    background = _color(colors[1] if len(colors) > 1 else None, "#08090b")
    accent = _color(colors[2] if len(colors) > 2 else None, "#4d9bff")

    image = Image.new("RGB", (width, height), background)
    pixels = image.load()
    for y in range(height):
        blend = y / max(1, height - 1)
        shade = tuple(max(0, min(255, int(channel * (1 - 0.22 * blend)))) for channel in background)
        for x in range(width):
            pixels[x, y] = shade

    canvas = image.convert("RGBA")
    draw = ImageDraw.Draw(canvas, "RGBA")
    margin = max(72, width // 12)
    draw.ellipse(
        (width * 0.58, -height * 0.34, width * 1.15, height * 0.5),
        fill=(*primary, 52),
    )
    draw.ellipse(
        (-width * 0.2, height * 0.62, width * 0.42, height * 1.25),
        fill=(*accent, 24),
    )
    for offset in range(0, width, max(52, width // 24)):
        draw.line((offset, 0, offset - height, height), fill=(*accent, 10), width=1)

    logo = _brand_logo(workspace, max(88, width // 9))
    business = str(workspace.get("business_name") or "Socium workspace")[:120]
    label_font = _font(max(22, width // 52), bold=True)
    body_font = _font(max(24, width // 45))
    title_font = _font(max(48, width // 20), bold=True)
    small_font = _font(max(18, width // 62))

    draw.rounded_rectangle(
        (margin, margin, width - margin, height - margin),
        radius=max(28, width // 42),
        fill=(3, 5, 8, 196),
        outline=(*primary, 95),
        width=max(2, width // 500),
    )
    header_y = margin + max(38, width // 38)
    draw.text((margin + 42, header_y), business.upper(), font=label_font, fill=(238, 242, 248, 255))
    if logo is not None:
        logo_x = width - margin - 42 - logo.width
        logo_y = header_y - max(8, logo.height // 8)
        canvas.alpha_composite(logo, (logo_x, logo_y))

    line_y = header_y + max(62, width // 20)
    draw.line((margin + 42, line_y, width - margin - 42, line_y), fill=(*primary, 110), width=2)
    draw.text(
        (margin + 42, line_y + max(36, height // 30)),
        "PRACTICAL SECURITY INSIGHT",
        font=small_font,
        fill=(*accent, 255),
    )

    title = str(content.get("title") or "A practical update")[:240]
    title_lines = _wrap(draw, title, title_font, width - (margin + 42) * 2, 4)
    title_y = line_y + max(90, height // 12)
    title_step = int(title_font.size * 1.16) if hasattr(title_font, "size") else 60
    for index, line in enumerate(title_lines):
        draw.text(
            (margin + 42, title_y + index * title_step),
            line,
            font=title_font,
            fill=(248, 250, 252, 255),
        )

    cta = str(
        content.get("call_to_action")
        or content.get("callToAction")
        or workspace.get("call_to_action")
        or ""
    )[:500]
    footer_y = height - margin - max(145, height // 7)
    if cta:
        cta_lines = _wrap(draw, cta, body_font, width - (margin + 42) * 2, 2)
        for index, line in enumerate(cta_lines):
            draw.text(
                (margin + 42, footer_y + index * max(36, body_font.size + 8)),
                line,
                font=body_font,
                fill=(205, 213, 224, 255),
            )
    website = str(workspace.get("website") or "")[:180]
    if website:
        website = website.removeprefix("https://").removeprefix("http://").rstrip("/")
        draw.text(
            (margin + 42, height - margin - 54),
            website,
            font=small_font,
            fill=(*primary, 255),
        )

    output = BytesIO()
    canvas.convert("RGB").save(output, format="PNG", optimize=True)
    return output.getvalue()
