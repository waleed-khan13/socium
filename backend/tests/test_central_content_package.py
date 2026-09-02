from __future__ import annotations

import asyncio
import base64
from io import BytesIO

from PIL import Image


def _png_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (32, 24), color=(20, 184, 166)).save(output, format="PNG")
    return output.getvalue()


def test_one_primary_ai_builds_a_complete_post_package(client, monkeypatch) -> None:
    from app.media_store import delete_media_asset, media_asset_delivery
    from app.schemas import GeneratedContent
    from app.services import content_package
    from app.services.image_generation import GeneratedImage

    async def fake_content(_provider, request, workspace):
        assert request["channel"] == "linkedin"
        assert workspace["business_name"] == "CyberTool.dev"
        return GeneratedContent(
            title="A complete campaign package",
            body="One connected AI produced this reviewed post.",
            hashtags=["Socium", "LocalFirst"],
            call_to_action="Review the full package.",
            image_prompt="A secure local marketing workspace in a dark editorial style",
            image_negative_prompt="watermark, distorted text",
            image_alt_text="A secure local marketing workspace",
            rationale="Tests the centralized generation boundary.",
        )

    captured: dict = {}

    async def fake_image(settings, request):
        captured["settings"] = settings
        captured["request"] = request
        return GeneratedImage(
            data=_png_bytes(),
            provider_kind="gemini-images",
            model="gemini-3.1-flash-image",
            parameters={"aspectRatio": "16:9"},
        )

    monkeypatch.setattr(content_package, "generate_content", fake_content)
    monkeypatch.setattr(content_package, "generate_image", fake_image)
    monkeypatch.setattr(
        content_package,
        "primary_image_runtime",
        lambda: {
            "kind": "gemini-images",
            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
            "model": "gemini-3.1-flash-image",
            "api_key": "same-primary-key",
        },
    )
    package = asyncio.run(
        content_package.generate_post_package(
            {"kind": "gemini", "model": "gemini-text", "api_key": "same-primary-key"},
            {"topic": "Security", "channel": "linkedin"},
            {"business_name": "CyberTool.dev"},
        )
    )
    assert package.content.hashtags == ["Socium", "LocalFirst"]
    assert captured["settings"]["api_key"] == "same-primary-key"
    assert captured["request"].prompt == package.content.image_prompt
    assert captured["request"].preset == "landscape"
    saved = media_asset_delivery(package.media_asset_id)
    assert saved["data"] == _png_bytes()
    assert saved["altText"] == package.content.image_alt_text
    delete_media_asset(package.media_asset_id)


def test_image_quota_failure_uses_a_private_local_brand_visual(client, monkeypatch) -> None:
    from app.errors import ExternalServiceError
    from app.media_store import delete_media_asset, media_asset_delivery
    from app.schemas import ImageGenerateRequest
    from app.services import content_package

    async def unavailable_image(_settings, _request):
        raise ExternalServiceError("Image quota is unavailable for this connection.")

    monkeypatch.setattr(content_package, "generate_image", unavailable_image)
    monkeypatch.setattr(
        content_package,
        "primary_image_runtime",
        lambda: {
            "kind": "gemini-images",
            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
            "model": "gemini-3.1-flash-image",
            "api_key": "same-primary-key",
        },
    )
    asset_id, provider_kind, model = asyncio.run(
        content_package._generate_and_store_image(
            ImageGenerateRequest(
                prompt="A practical developer-security campaign visual",
                altText="A branded developer-security campaign card",
                preset="landscape",
            ),
            {
                "title": "Scan security issues before release",
                "call_to_action": "Scan a public repository free.",
            },
            {
                "business_name": "CyberTool.dev",
                "website": "https://cybertool.dev",
                "brand_colors": ["#006efe", "#0f0f0f", "#4d9bff"],
            },
        )
    )
    assert provider_kind == "socium-local"
    assert model == "brand-card-v1"
    saved = media_asset_delivery(asset_id)
    assert saved["mimeType"] == "image/png"
    assert saved["altText"] == "A branded developer-security campaign card"
    with Image.open(BytesIO(saved["data"])) as rendered:
        assert rendered.size == (1536, 1024)
    delete_media_asset(asset_id)


def test_gemini_image_adapter_uses_native_generate_content_contract(monkeypatch) -> None:
    from app.schemas import ImageGenerateRequest
    from app.services import image_generation

    calls: list[dict] = []

    async def fake_request(url: str, **kwargs):
        calls.append({"url": url, **kwargs})
        return {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "inlineData": {
                                    "mimeType": "image/png",
                                    "data": base64.b64encode(_png_bytes()).decode("ascii"),
                                }
                            }
                        ]
                    }
                }
            ]
        }

    monkeypatch.setattr(image_generation, "_request_json", fake_request)
    result = asyncio.run(
        image_generation.generate_image(
            {
                "kind": "gemini-images",
                "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
                "model": "gemini-3.1-flash-image",
                "api_key": "primary-key",
            },
            ImageGenerateRequest(
                prompt="A campaign image",
                negativePrompt="watermark",
                preset="landscape",
            ),
        )
    )
    assert result.data == _png_bytes()
    assert calls[0]["url"].endswith(
        "/v1/models/gemini-3.1-flash-image:generateContent"
    )
    assert calls[0]["headers"]["x-goog-api-key"] == "primary-key"
    body = calls[0]["json_body"]
    assert body["generationConfig"]["responseModalities"] == ["IMAGE"]
    assert (
        body["generationConfig"]["responseFormat"]["image"]["aspectRatio"]
        == "ASPECT_RATIO_SIXTEEN_BY_NINE"
    )
    assert (
        body["generationConfig"]["responseFormat"]["image"]["imageSize"]
        == "IMAGE_SIZE_ONE_K"
    )


def test_approval_messages_include_image_and_independent_regeneration(monkeypatch) -> None:
    from app.services.slack import send_approval_message
    from app.services.telegram import send_approval_request

    telegram_fields: dict = {}
    slack_body: dict = {}

    async def fake_telegram_upload(_token, method, fields, **kwargs):
        assert method == "sendPhoto"
        assert kwargs["data"] == b"image"
        telegram_fields.update(fields)
        return {"message_id": 42}

    async def fake_slack_upload(*_args, **_kwargs):
        return "F123IMAGE"

    async def fake_slack_request(_token, method, body, **_kwargs):
        assert method == "chat.postMessage"
        slack_body.update(body)
        return {"ok": True, "ts": "123.456"}

    fake_media = {
        "filename": "campaign.png",
        "data": b"image",
        "mimeType": "image/png",
        "byteSize": 5,
        "altText": "Campaign visual",
    }
    monkeypatch.setattr("app.services.telegram.media_asset_delivery", lambda _id: fake_media)
    monkeypatch.setattr("app.services.telegram.telegram_upload_request", fake_telegram_upload)
    monkeypatch.setattr("app.services.slack.upload_approval_image", fake_slack_upload)
    monkeypatch.setattr("app.services.slack.slack_request", fake_slack_request)
    post = {
        "id": "post-with-image",
        "revision": 3,
        "channel": "linkedin",
        "title": "Review the full package",
        "body": "Caption and image travel together.",
        "hashtags": ["Socium"],
        "mediaAssetId": "asset-id",
        "imageAltText": "Campaign visual",
    }
    assert asyncio.run(send_approval_request("token", "chat", post, "action")) == "42"
    assert asyncio.run(send_approval_message("token", "channel", post, "action")) == "123.456"
    assert "caption" in telegram_fields
    slack_image = next(block for block in slack_body["blocks"] if block["type"] == "image")
    assert slack_image["slack_file"] == {"id": "F123IMAGE"}
    action_values = [item["value"] for item in slack_body["blocks"][-1]["elements"]]
    assert "sa:p:action" in action_values
    assert "sa:i:action" in action_values
