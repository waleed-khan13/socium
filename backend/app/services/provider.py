from __future__ import annotations

import json
import time
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from app.errors import ExternalServiceError
from app.schemas import GeneratedContent, GeneratedOutreach, ProviderConnectionResult

HOSTED_PROVIDER_URLS = {
    "openai": "https://api.openai.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "anthropic": "https://api.anthropic.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "nvidia": "https://integrate.api.nvidia.com/v1",
}

PROVIDER_NAMES = {
    "ollama": "Ollama",
    "openai": "OpenAI",
    "gemini": "Google Gemini",
    "anthropic": "Anthropic",
    "anthropic-compatible": "Anthropic-compatible provider",
    "openrouter": "OpenRouter",
    "nvidia": "NVIDIA NIM",
    "openai-compatible": "Provider",
}


def validate_base_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ExternalServiceError("Provider URL must be a valid http or https address.")
    if parsed.username or parsed.password:
        raise ExternalServiceError("Provider URL credentials are not allowed. Use the API key field instead.")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


def validate_provider_base_url(kind: str, value: str) -> str:
    normalized = validate_base_url(value)
    expected = HOSTED_PROVIDER_URLS.get(kind)
    if expected and normalized != expected:
        raise ExternalServiceError(
            f"{PROVIDER_NAMES[kind]} uses a fixed official API endpoint. Select the custom adapter "
            "to use another URL."
        )
    return normalized


def _openai_endpoint(base_url: str, resource: str) -> str:
    normalized = validate_base_url(base_url)
    return f"{normalized}/{resource}" if normalized.endswith("/v1") else f"{normalized}/v1/{resource}"


def _provider_endpoint(settings: dict[str, str], resource: str) -> str:
    if settings["kind"] in {"openai-compatible", "anthropic-compatible"}:
        return _openai_endpoint(settings["base_url"], resource)
    return f"{validate_provider_base_url(settings['kind'], settings['base_url'])}/{resource}"


def _provider_headers(settings: dict[str, str]) -> dict[str, str]:
    api_key = settings["api_key"]
    if settings["kind"] in {"anthropic", "anthropic-compatible"}:
        return {
            **({"x-api-key": api_key} if api_key else {}),
            "anthropic-version": "2023-06-01",
        }
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    if settings["kind"] == "openrouter":
        headers["X-Title"] = "Socium"
    return headers


async def _request_json(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout: float = 25,
) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(follow_redirects=False, timeout=timeout) as client:
            response = await client.request(
                method, url, headers={"Accept": "application/json", **(headers or {})}, json=json_body
            )
    except httpx.HTTPError as error:
        raise ExternalServiceError(f"Provider connection failed ({type(error).__name__}).") from error
    try:
        payload = response.json()
    except ValueError as error:
        raise ExternalServiceError(
            f"Provider returned a non-JSON response ({response.status_code})."
        ) from error
    if not response.is_success:
        message = ""
        if isinstance(payload, dict):
            nested = payload.get("error")
            if isinstance(nested, dict):
                message = str(nested.get("message") or "")
            message = message or str(payload.get("message") or "")
        raise ExternalServiceError(message or f"Provider returned HTTP {response.status_code}.")
    if not isinstance(payload, dict):
        raise ExternalServiceError("Provider returned an invalid JSON object.")
    return payload


async def test_provider(settings: dict[str, str]) -> ProviderConnectionResult:
    started = time.monotonic()
    try:
        if settings["kind"] == "ollama":
            payload = await _request_json(f"{validate_base_url(settings['base_url'])}/api/tags")
            raw_models = payload.get("models") if isinstance(payload.get("models"), list) else []
            models = [
                str(item.get("name")) for item in raw_models if isinstance(item, dict) and item.get("name")
            ]
            message = (
                f"Ollama connected. {len(models)} local model(s) found."
                if models
                else "Ollama connected. Pull a model to generate content."
            )
        else:
            payload = await _request_json(
                _provider_endpoint(settings, "models"),
                headers=_provider_headers(settings),
            )
            raw_models = payload.get("data") if isinstance(payload.get("data"), list) else []
            models = [
                str(item.get("id")) for item in raw_models if isinstance(item, dict) and item.get("id")
            ][:50]
            provider_name = PROVIDER_NAMES.get(settings["kind"], "Provider")
            message = f"{provider_name} connected"
            if models:
                message += f" with {len(models)} visible model(s)"
            message += "."
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


def _models_from_payload(payload: dict[str, Any], kind: str) -> list[str]:
    key, identifier = ("models", "name") if kind == "ollama" else ("data", "id")
    raw_models = payload.get(key) if isinstance(payload.get(key), list) else []
    return [
        str(item.get(identifier)) for item in raw_models if isinstance(item, dict) and item.get(identifier)
    ][:50]


async def discover_provider(
    base_url: str,
    protocol_hint: str = "auto",
    api_key: str = "",
) -> dict[str, Any]:
    """Detect one provider contract without sending a key to multiple protocols."""
    normalized = validate_base_url(base_url)
    started = time.monotonic()
    if protocol_hint != "auto":
        result = await test_provider(
            {
                "kind": protocol_hint,
                "base_url": normalized,
                "model": "",
                "api_key": api_key,
            }
        )
        return {
            "ok": result.ok,
            "status": "detected" if result.ok else "failed",
            "detectedKind": protocol_hint if result.ok else None,
            "normalizedBaseUrl": normalized,
            "models": result.models or [],
            "message": result.message,
            "requiresProtocolChoice": False,
            "candidates": [],
            "local": protocol_hint == "ollama",
            "latencyMs": result.latency_ms,
        }

    # Auto detection is intentionally credential-free. If authentication blocks
    # inspection, the operator must choose one protocol before the key is used.
    try:
        payload = await _request_json(f"{normalized}/api/tags", timeout=4)
        if isinstance(payload.get("models"), list):
            models = _models_from_payload(payload, "ollama")
            return {
                "ok": True,
                "status": "detected",
                "detectedKind": "ollama",
                "normalizedBaseUrl": normalized,
                "models": models,
                "message": f"Ollama detected with {len(models)} installed model(s).",
                "requiresProtocolChoice": False,
                "candidates": [],
                "local": True,
                "latencyMs": round((time.monotonic() - started) * 1_000),
            }
    except ExternalServiceError:
        pass

    try:
        payload = await _request_json(_openai_endpoint(normalized, "models"), timeout=6)
        raw_models = payload.get("data") if isinstance(payload.get("data"), list) else []
        if raw_models:
            first = raw_models[0] if isinstance(raw_models[0], dict) else {}
            detected = (
                "anthropic-compatible"
                if "display_name" in first and "owned_by" not in first
                else "openai-compatible"
            )
            models = _models_from_payload(payload, detected)
            local = normalized.startswith(("http://127.0.0.1", "http://localhost", "http://[::1]"))
            return {
                "ok": True,
                "status": "detected",
                "detectedKind": detected,
                "normalizedBaseUrl": normalized,
                "models": models,
                "message": f"{PROVIDER_NAMES[detected]} detected with {len(models)} model(s).",
                "requiresProtocolChoice": False,
                "candidates": [],
                "local": local,
                "latencyMs": round((time.monotonic() - started) * 1_000),
            }
    except ExternalServiceError:
        pass

    return {
        "ok": False,
        "status": "needs-protocol",
        "detectedKind": None,
        "normalizedBaseUrl": normalized,
        "models": [],
        "message": (
            "The endpoint needs authentication or has no recognizable public model list. "
            "Choose its API protocol, then run one scoped test."
        ),
        "requiresProtocolChoice": True,
        "candidates": ["openai-compatible", "anthropic-compatible", "ollama"],
        "local": normalized.startswith(("http://127.0.0.1", "http://localhost", "http://[::1]")),
        "latencyMs": round((time.monotonic() - started) * 1_000),
    }


def _generation_prompt(request: dict[str, Any], workspace: dict[str, Any]) -> str:
    lines = [
            "You are the senior social media copywriter inside a human-approved marketing workflow.",
            "Return only valid JSON with this exact shape:",
            '{"title":"short internal title","body":"publish-ready post","hashtags":["#tag"],"rationale":"one sentence explaining the angle"}',
            "Do not invent statistics, testimonials, customers, awards, prices, or guarantees.",
            "Avoid generic AI phrases, excessive punctuation, and engagement bait.",
            f"Business: {workspace['business_name'] or 'Not provided'}",
            f"Business context: {workspace['business_description'] or 'Not provided'}",
    ]
    if workspace.get("profile_confirmed"):
        lines.extend(
            [
                f"Confirmed brand profile revision: {workspace.get('profile_version')}",
                f"Website: {workspace.get('website') or 'Not provided'}",
                f"Industry: {workspace.get('industry') or 'Not provided'}",
                f"Products or services: {workspace.get('products_services')}",
                f"Target audience: {workspace.get('target_audience')}",
                f"Business location: {workspace.get('location') or 'Not provided'}",
                f"Marketing goals: {'; '.join(workspace.get('goals') or [])}",
                f"Default call to action: {workspace.get('call_to_action')}",
                f"Preferred language: {workspace.get('language')}",
                f"Brand voice: {workspace.get('tone')}",
                f"Content pillars: {'; '.join(workspace.get('content_pillars') or [])}",
                f"Restricted claims or topics: {'; '.join(workspace.get('restricted_claims') or []) or 'None provided'}",
                f"Branded hashtags: {' '.join(workspace.get('branded_hashtags') or []) or 'None provided'}",
                f"Visual direction: {workspace.get('visual_style') or 'Not provided'}",
                f"Brand colors: {', '.join(workspace.get('brand_colors') or [])}",
                "Treat restricted claims as prohibited. Use the default CTA and branded hashtags only when relevant.",
            ]
        )
    lines.extend(
        [
            f"Channel: {request['channel']}",
            f"Topic: {request['topic']}",
            f"Objective: {request['objective'] or 'Build useful awareness'}",
            f"Tone: {request['tone'] or 'Clear and confident'}",
            "Adapt length, structure, and hashtag count to the selected channel.",
        ]
    )
    return "\n".join(lines)


def _parse_content(value: str) -> GeneratedContent:
    cleaned = value.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        cleaned = cleaned.rsplit("```", 1)[0]
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        raise ExternalServiceError("Model did not return valid JSON content.")
    try:
        payload = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as error:
        raise ExternalServiceError("Model did not return valid JSON content.") from error
    if not isinstance(payload, dict):
        raise ExternalServiceError("Model returned an invalid content object.")
    title = str(payload.get("title") or "").strip()[:160]
    body = str(payload.get("body") or "").strip()[:12_000]
    raw_tags = payload.get("hashtags") if isinstance(payload.get("hashtags"), list) else []
    hashtags = [str(tag).strip()[:80] for tag in raw_tags if str(tag).strip()][:20]
    rationale = str(payload.get("rationale") or "").strip()[:500]
    if not title or not body:
        raise ExternalServiceError("Model response is missing a title or body.")
    return GeneratedContent(title=title, body=body, hashtags=hashtags, rationale=rationale)


def _outreach_prompt(request: dict[str, Any], lead: dict[str, object], workspace: dict[str, str]) -> str:
    return "\n".join(
        [
            "You draft respectful business-to-business email for a human-reviewed workflow.",
            "Return only valid JSON with this exact shape:",
            '{"subject":"specific subject","body":"plain-text email","rationale":"one sentence explaining the angle"}',
            "Never claim the email was sent. Never invent facts, relationships, results, or familiarity.",
            "Do not use manipulative urgency, misleading Re: prefixes, or unsupported personalization.",
            f"Sender business: {workspace['business_name'] or 'Not provided'}",
            f"Sender context: {workspace['business_description'] or 'Not provided'}",
            f"Recipient business: {lead.get('businessName') or 'Not provided'}",
            f"Recipient website: {lead.get('website') or 'Not provided'}",
            f"Recipient location: {lead.get('location') or 'Not provided'}",
            f"Public research notes: {lead.get('notes') or 'Not provided'}",
            f"Objective: {request['objective']}",
            f"Tone: {request['tone']}",
            "Keep the message concise, transparent about the sender, and easy to decline.",
        ]
    )


def _parse_outreach(value: str) -> GeneratedOutreach:
    cleaned = value.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        cleaned = cleaned.rsplit("```", 1)[0]
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        raise ExternalServiceError("Model did not return a valid outreach JSON object.")
    try:
        payload = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as error:
        raise ExternalServiceError("Model did not return a valid outreach JSON object.") from error
    if not isinstance(payload, dict):
        raise ExternalServiceError("Model returned an invalid outreach object.")
    subject = str(payload.get("subject") or "").strip()[:200]
    body = str(payload.get("body") or "").strip()[:12_000]
    rationale = str(payload.get("rationale") or "").strip()[:500]
    if not subject or not body:
        raise ExternalServiceError("Model response is missing an outreach subject or body.")
    return GeneratedOutreach(subject=subject, body=body, rationale=rationale)


async def _generate_json_text(
    settings: dict[str, str], prompt: str, *, system_prompt: str, temperature: float
) -> str:
    if settings["kind"] == "ollama":
        payload = await _request_json(
            f"{validate_base_url(settings['base_url'])}/api/chat",
            method="POST",
            headers={"Content-Type": "application/json"},
            json_body={
                "model": settings["model"],
                "stream": False,
                "format": "json",
                "messages": [{"role": "user", "content": prompt}],
                "options": {"temperature": temperature},
                "keep_alive": "2m",
            },
            timeout=120,
        )
        message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
        return str(message.get("content") or "")

    if settings["kind"] in {"anthropic", "anthropic-compatible"}:
        payload = await _request_json(
            _provider_endpoint(settings, "messages"),
            method="POST",
            headers={"Content-Type": "application/json", **_provider_headers(settings)},
            json_body={
                "model": settings["model"],
                "max_tokens": 4_096,
                "temperature": temperature,
                "system": system_prompt,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=120,
        )
        blocks = payload.get("content") if isinstance(payload.get("content"), list) else []
        return "\n".join(
            str(block.get("text") or "")
            for block in blocks
            if isinstance(block, dict) and block.get("type") == "text"
        )

    headers = {"Content-Type": "application/json", **_provider_headers(settings)}
    request_body: dict[str, Any] = {
        "model": settings["model"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
    }
    if settings["kind"] != "openai":
        request_body["temperature"] = temperature
    payload = await _request_json(
        _provider_endpoint(settings, "chat/completions"),
        method="POST",
        headers=headers,
        json_body=request_body,
        timeout=120,
    )
    choices = payload.get("choices") if isinstance(payload.get("choices"), list) else []
    message = choices[0].get("message") if choices and isinstance(choices[0], dict) else {}
    return str(message.get("content") or "") if isinstance(message, dict) else ""


async def generate_content(
    settings: dict[str, str], request: dict[str, Any], workspace: dict[str, Any]
) -> GeneratedContent:
    if not settings["model"]:
        raise ExternalServiceError("Select a model before generating content.")
    prompt = _generation_prompt(request, workspace)
    content = await _generate_json_text(
        settings,
        prompt,
        system_prompt="You create factual, brand-safe marketing drafts for human review.",
        temperature=0.7,
    )
    return _parse_content(content)


async def generate_outreach(
    settings: dict[str, str],
    request: dict[str, Any],
    lead: dict[str, object],
    workspace: dict[str, str],
) -> GeneratedOutreach:
    if not settings["model"]:
        raise ExternalServiceError("Select a model before generating outreach.")
    content = await _generate_json_text(
        settings,
        _outreach_prompt(request, lead, workspace),
        system_prompt="You write factual outreach drafts that require explicit human approval before export.",
        temperature=0.5,
    )
    return _parse_outreach(content)
