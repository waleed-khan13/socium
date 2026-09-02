from __future__ import annotations

import asyncio
import base64
import binascii
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlsplit

import httpx

from app.errors import ExternalServiceError
from app.schemas import ImageGenerateRequest, ProviderConnectionResult
from app.services.provider import _openai_endpoint, _request_json, validate_base_url

MAX_GENERATED_IMAGE_BYTES = 10 * 1024 * 1024
MAX_ENCODED_IMAGE_LENGTH = ((MAX_GENERATED_IMAGE_BYTES + 2) // 3) * 4 + 128

OPENAI_SIZES = {
    "square": "1024x1024",
    "portrait": "1024x1536",
    "landscape": "1536x1024",
}
GEMINI_ASPECT_RATIOS = {
    "square": "1:1",
    "portrait": "4:5",
    "landscape": "16:9",
}
GEMINI_ASPECT_RATIO_ENUMS = {
    "square": "ASPECT_RATIO_ONE_BY_ONE",
    "portrait": "ASPECT_RATIO_FOUR_BY_FIVE",
    "landscape": "ASPECT_RATIO_SIXTEEN_BY_NINE",
}
A1111_SIZES = {
    "square": (1024, 1024),
    "portrait": (896, 1152),
    "landscape": (1152, 896),
}
COMFY_PLACEHOLDERS = {
    "{{prompt}}",
    "{{negative_prompt}}",
    "{{seed}}",
    "{{width}}",
    "{{height}}",
    "{{steps}}",
    "{{guidance_scale}}",
    "{{model}}",
}

ProgressCallback = Callable[[int, str], None]
CancelCheck = Callable[[], bool]
RemoteRefCallback = Callable[[str], None]


class GenerationCancelled(Exception):
    pass


@dataclass(frozen=True)
class GeneratedImage:
    data: bytes
    provider_kind: str
    model: str
    parameters: dict[str, Any]


def validate_image_base_url(value: str) -> str:
    return validate_base_url(value)


def _headers(api_key: str, provider_kind: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        if provider_kind == "gemini-images":
            headers["x-goog-api-key"] = api_key
        elif provider_kind == "automatic1111" and ":" in api_key:
            encoded = base64.b64encode(api_key.encode("utf-8")).decode("ascii")
            headers["Authorization"] = f"Basic {encoded}"
        else:
            headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _gemini_image_endpoint(base_url: str, model: str) -> str:
    parsed = urlsplit(validate_base_url(base_url))
    clean_model = model.removeprefix("models/")
    return f"{parsed.scheme}://{parsed.netloc}/v1/models/{quote(clean_model, safe='.-_')}:generateContent"


def _gemini_image_data(payload: dict[str, Any]) -> bytes:
    candidates = payload.get("candidates")
    first = candidates[0] if isinstance(candidates, list) and candidates else {}
    content = first.get("content") if isinstance(first, dict) else {}
    parts = content.get("parts") if isinstance(content, dict) else []
    for part in parts if isinstance(parts, list) else []:
        if not isinstance(part, dict):
            continue
        inline = part.get("inlineData") or part.get("inline_data")
        if isinstance(inline, dict) and inline.get("data"):
            return _decode_image(inline["data"])
    feedback = payload.get("promptFeedback") or payload.get("prompt_feedback")
    suffix = f" Provider feedback: {str(feedback)[:300]}" if feedback else ""
    raise ExternalServiceError(f"Gemini did not return generated image data.{suffix}")


def _progress(callback: ProgressCallback | None, percent: int, message: str) -> None:
    if callback is not None:
        callback(percent, message)


def _is_cancelled(check: CancelCheck | None) -> bool:
    return bool(check and check())


async def _await_cancellable(coroutine, cancel_check: CancelCheck | None):  # type: ignore[no-untyped-def]
    task = asyncio.create_task(coroutine)
    try:
        while not task.done():
            done, _ = await asyncio.wait({task}, timeout=0.25)
            if done:
                break
            if _is_cancelled(cancel_check):
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                raise GenerationCancelled
        return await task
    except Exception:
        if not task.done():
            task.cancel()
        raise


def _render_comfy_value(value: object, replacements: dict[str, object]) -> object:
    if isinstance(value, dict):
        return {key: _render_comfy_value(item, replacements) for key, item in value.items()}
    if isinstance(value, list):
        return [_render_comfy_value(item, replacements) for item in value]
    if not isinstance(value, str):
        return value
    if value in replacements:
        return replacements[value]
    rendered = value
    for placeholder, replacement in replacements.items():
        rendered = rendered.replace(placeholder, str(replacement))
    return rendered


def _render_comfy_workflow(settings: dict[str, str], request: ImageGenerateRequest) -> dict[str, Any]:
    try:
        workflow = json.loads(settings.get("workflow_json") or "")
    except json.JSONDecodeError as error:
        raise ExternalServiceError("Saved ComfyUI workflow is not valid JSON.") from error
    if not isinstance(workflow, dict) or not workflow:
        raise ExternalServiceError("Save a ComfyUI workflow exported in API format first.")
    width, height = A1111_SIZES[request.preset]
    replacements: dict[str, object] = {
        "{{prompt}}": request.prompt,
        "{{negative_prompt}}": request.negative_prompt,
        "{{seed}}": request.seed,
        "{{width}}": width,
        "{{height}}": height,
        "{{steps}}": request.steps,
        "{{guidance_scale}}": request.guidance_scale,
        "{{model}}": settings.get("model") or "",
    }
    rendered = _render_comfy_value(workflow, replacements)
    serialized = json.dumps(rendered, separators=(",", ":"))
    remaining = sorted(item for item in COMFY_PLACEHOLDERS if item in serialized)
    if remaining:
        raise ExternalServiceError(f"ComfyUI workflow contains unresolved placeholders: {', '.join(remaining)}")
    return rendered  # type: ignore[return-value]


def _comfy_output(history: dict[str, Any]) -> dict[str, str] | None:
    outputs = history.get("outputs")
    if not isinstance(outputs, dict):
        return None
    for output in outputs.values():
        if not isinstance(output, dict):
            continue
        images = output.get("images")
        if not isinstance(images, list):
            continue
        for image in images:
            if isinstance(image, dict) and image.get("filename"):
                return {
                    "filename": str(image["filename"]),
                    "subfolder": str(image.get("subfolder") or ""),
                    "type": str(image.get("type") or "output"),
                }
    return None


async def _request_image_bytes(
    url: str,
    *,
    headers: dict[str, str],
    params: dict[str, str],
) -> bytes:
    try:
        async with (
            httpx.AsyncClient(follow_redirects=False, timeout=60) as client,
            client.stream("GET", url, headers=headers, params=params) as response,
        ):
            if response.status_code >= 400:
                raise ExternalServiceError(
                    f"ComfyUI image download failed with HTTP {response.status_code}."
                )
            chunks: list[bytes] = []
            total = 0
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                if total > MAX_GENERATED_IMAGE_BYTES:
                    raise ExternalServiceError(
                        "Generated image is larger than the 10 MB local media limit."
                    )
                chunks.append(chunk)
    except httpx.HTTPError as error:
        raise ExternalServiceError("Could not download the completed image from ComfyUI.") from error
    data = b"".join(chunks)
    if not data:
        raise ExternalServiceError("ComfyUI returned an empty image.")
    return data


def _decode_image(value: object) -> bytes:
    if not isinstance(value, str) or not value:
        raise ExternalServiceError("Image provider response did not include image data.")
    encoded = value.split(",", 1)[1] if value.startswith("data:") and "," in value else value
    if len(encoded) > MAX_ENCODED_IMAGE_LENGTH:
        raise ExternalServiceError("Generated image is larger than the 10 MB local media limit.")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ExternalServiceError("Image provider returned invalid base64 image data.") from error
    if not data:
        raise ExternalServiceError("Image provider returned an empty image.")
    if len(data) > MAX_GENERATED_IMAGE_BYTES:
        raise ExternalServiceError("Generated image is larger than the 10 MB local media limit.")
    return data


async def test_image_provider(settings: dict[str, str]) -> ProviderConnectionResult:
    started = time.monotonic()
    try:
        headers = _headers(settings["api_key"], settings["kind"])
        if settings["kind"] == "gemini-images":
            parsed = urlsplit(validate_image_base_url(settings["base_url"]))
            version = "v1beta" if "/v1beta" in parsed.path else "v1"
            payload = await _request_json(
                f"{parsed.scheme}://{parsed.netloc}/{version}/models",
                headers=headers,
            )
            available = payload.get("models") if isinstance(payload.get("models"), list) else []
            models = [str(item.get("name") or "").removeprefix("models/") for item in available if isinstance(item, dict)]
            if settings["model"] not in models:
                raise ExternalServiceError(
                    f"The connected Gemini account does not currently expose {settings['model']}."
                )
            message = "Gemini image generation is available through the main AI connection."
        elif settings["kind"] == "comfyui":
            payload = await _request_json(
                f"{validate_image_base_url(settings['base_url'])}/system_stats",
                headers=headers,
            )
            devices = payload.get("devices") if isinstance(payload.get("devices"), list) else []
            models = [str(item.get("name")) for item in devices if isinstance(item, dict) and item.get("name")]
            message = "ComfyUI API connected; workflow is ready to queue."
        elif settings["kind"] == "automatic1111":
            payload = await _request_json(
                f"{validate_image_base_url(settings['base_url'])}/sdapi/v1/options",
                headers=headers,
            )
            current_model = str(payload.get("sd_model_checkpoint") or "").strip()
            models = [current_model] if current_model else []
            message = "Automatic1111 / Forge API connected."
        else:
            payload = await _request_json(
                _openai_endpoint(settings["base_url"], "models"),
                headers=headers,
            )
            raw_models = payload.get("data") if isinstance(payload.get("data"), list) else []
            models = [
                str(item.get("id")) for item in raw_models if isinstance(item, dict) and item.get("id")
            ][:100]
            message = "OpenAI-compatible Images API connected."
        return ProviderConnectionResult(
            ok=True,
            message=message,
            models=models,
            latency_ms=round((time.monotonic() - started) * 1_000),
        )
    except ExternalServiceError as error:
        return ProviderConnectionResult(
            ok=False,
            message=error.message,
            latency_ms=round((time.monotonic() - started) * 1_000),
        )


async def generate_image(
    settings: dict[str, str],
    request: ImageGenerateRequest,
    *,
    progress: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
    remote_ref: RemoteRefCallback | None = None,
) -> GeneratedImage:
    headers = _headers(settings["api_key"], settings["kind"])
    if _is_cancelled(cancel_check):
        raise GenerationCancelled
    if settings["kind"] == "gemini-images":
        _progress(progress, 15, "Creating the campaign image with the connected Gemini account.")
        prompt = request.prompt
        if request.negative_prompt:
            prompt = f"{prompt}\n\nAvoid: {request.negative_prompt}"
        payload = await _await_cancellable(
            _request_json(
                _gemini_image_endpoint(settings["base_url"], settings["model"]),
                method="POST",
                headers=headers,
                json_body={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "responseModalities": ["IMAGE"],
                        "responseFormat": {
                            "image": {
                                "aspectRatio": GEMINI_ASPECT_RATIO_ENUMS[request.preset],
                                "imageSize": "IMAGE_SIZE_ONE_K",
                            }
                        },
                    },
                },
                timeout=300,
                max_attempts=1,
            ),
            cancel_check,
        )
        _progress(progress, 85, "Validating the Gemini image.")
        return GeneratedImage(
            data=_gemini_image_data(payload),
            provider_kind="gemini-images",
            model=settings["model"],
            parameters={
                "preset": request.preset,
                "aspectRatio": GEMINI_ASPECT_RATIOS[request.preset],
                "imageSize": "1K",
            },
        )
    if settings["kind"] == "comfyui":
        base_url = validate_image_base_url(settings["base_url"])
        workflow = _render_comfy_workflow(settings, request)
        _progress(progress, 10, "Submitting workflow to ComfyUI.")
        queued = await _await_cancellable(
            _request_json(
                f"{base_url}/prompt",
                method="POST",
                headers=headers,
                json_body={"prompt": workflow},
                timeout=30,
            ),
            cancel_check,
        )
        prompt_id = str(queued.get("prompt_id") or "")
        if not prompt_id:
            node_errors = queued.get("node_errors")
            detail = f" Node errors: {json.dumps(node_errors)[:800]}" if node_errors else ""
            raise ExternalServiceError(f"ComfyUI rejected the workflow.{detail}")
        if remote_ref is not None:
            remote_ref(prompt_id)
        _progress(progress, 20, "Workflow queued in ComfyUI.")
        was_running = False
        output: dict[str, str] | None = None
        for _ in range(600):
            if _is_cancelled(cancel_check):
                try:
                    queue_state = await _request_json(f"{base_url}/queue", headers=headers, timeout=10)
                    running_now = (
                        queue_state.get("queue_running")
                        if isinstance(queue_state.get("queue_running"), list)
                        else []
                    )
                    target_running = was_running or any(
                        isinstance(item, list) and len(item) > 1 and str(item[1]) == prompt_id
                        for item in running_now
                    )
                    await _request_json(
                        f"{base_url}/queue",
                        method="POST",
                        headers=headers,
                        json_body={"delete": [prompt_id]},
                        timeout=10,
                    )
                    if target_running:
                        await _request_json(
                            f"{base_url}/interrupt",
                            method="POST",
                            headers=headers,
                            json_body={},
                            timeout=10,
                        )
                except ExternalServiceError:
                    pass
                raise GenerationCancelled
            history_payload = await _request_json(
                f"{base_url}/history/{prompt_id}",
                headers=headers,
                timeout=15,
            )
            history = history_payload.get(prompt_id)
            if isinstance(history, dict):
                output = _comfy_output(history)
                status = history.get("status") if isinstance(history.get("status"), dict) else {}
                if output:
                    break
                if status.get("status_str") in {"error", "failed"}:
                    raise ExternalServiceError("ComfyUI workflow execution failed; inspect its local console.")
            queue = await _request_json(f"{base_url}/queue", headers=headers, timeout=15)
            running = queue.get("queue_running") if isinstance(queue.get("queue_running"), list) else []
            pending = queue.get("queue_pending") if isinstance(queue.get("queue_pending"), list) else []
            was_running = any(isinstance(item, list) and len(item) > 1 and str(item[1]) == prompt_id for item in running)
            if was_running:
                _progress(progress, 55, "ComfyUI is executing the workflow.")
            else:
                position = next(
                    (
                        index + 1
                        for index, item in enumerate(pending)
                        if isinstance(item, list) and len(item) > 1 and str(item[1]) == prompt_id
                    ),
                    None,
                )
                _progress(
                    progress,
                    30,
                    f"Waiting in ComfyUI queue (position {position})." if position else "Waiting for ComfyUI output.",
                )
            await asyncio.sleep(0.5)
        if output is None:
            raise ExternalServiceError("ComfyUI workflow timed out before producing an image.")
        _progress(progress, 85, "Downloading and validating the ComfyUI output.")
        data = await _await_cancellable(
            _request_image_bytes(f"{base_url}/view", headers=headers, params=output),
            cancel_check,
        )
        width, height = A1111_SIZES[request.preset]
        return GeneratedImage(
            data=data,
            provider_kind="comfyui",
            model=settings.get("model") or "workflow",
            parameters={
                "preset": request.preset,
                "width": width,
                "height": height,
                "steps": request.steps,
                "guidanceScale": request.guidance_scale,
                "seed": request.seed,
                "promptId": prompt_id,
            },
        )
    if settings["kind"] == "automatic1111":
        width, height = A1111_SIZES[request.preset]
        model = settings["model"] or "active-checkpoint"
        body: dict[str, Any] = {
            "prompt": request.prompt,
            "negative_prompt": request.negative_prompt,
            "width": width,
            "height": height,
            "steps": request.steps,
            "cfg_scale": request.guidance_scale,
            "seed": request.seed,
            "batch_size": 1,
            "n_iter": 1,
        }
        if settings["model"]:
            body["override_settings"] = {"sd_model_checkpoint": settings["model"]}
            body["override_settings_restore_afterwards"] = True
        _progress(progress, 15, "Sending the request to Automatic1111 / Forge.")
        payload = await _await_cancellable(
            _request_json(
                f"{validate_image_base_url(settings['base_url'])}/sdapi/v1/txt2img",
                method="POST",
                headers=headers,
                json_body=body,
                timeout=300,
                max_attempts=1,
            ),
            cancel_check,
        )
        images = payload.get("images") if isinstance(payload.get("images"), list) else []
        encoded = images[0] if images else None
        parameters = {
            "preset": request.preset,
            "width": width,
            "height": height,
            "steps": request.steps,
            "guidanceScale": request.guidance_scale,
            "seed": request.seed,
        }
    else:
        if not settings["model"]:
            raise ExternalServiceError("Choose an image model before generating.")
        size = OPENAI_SIZES[request.preset]
        body = {
            "model": settings["model"],
            "prompt": request.prompt,
            "n": 1,
            "size": size,
            "quality": request.quality,
            "output_format": "png",
        }
        _progress(progress, 15, "Sending the request to the hosted image provider.")
        payload = await _await_cancellable(
            _request_json(
                _openai_endpoint(settings["base_url"], "images/generations"),
                method="POST",
                headers=headers,
                json_body=body,
                timeout=300,
                max_attempts=1,
            ),
            cancel_check,
        )
        results = payload.get("data") if isinstance(payload.get("data"), list) else []
        first = results[0] if results and isinstance(results[0], dict) else {}
        encoded = first.get("b64_json")
        model = settings["model"]
        parameters = {
            "preset": request.preset,
            "size": size,
            "quality": request.quality,
            "outputFormat": "png",
        }
    _progress(progress, 85, "Validating the provider image.")
    return GeneratedImage(
        data=_decode_image(encoded),
        provider_kind=settings["kind"],
        model=model,
        parameters=parameters,
    )
