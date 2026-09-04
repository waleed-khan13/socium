from __future__ import annotations

import time

from app.business_os_store import record_knowledge_analysis
from app.services.provider import _generation_prompt
from app.store import workspace_runtime


def test_business_profile_and_confirmed_knowledge_feed_the_workspace(client) -> None:
    profile_response = client.get("/api/workspaces/1/business")
    assert profile_response.status_code == 200
    assert profile_response.json()["profile"]["workspaceId"] == 1

    analysis = record_knowledge_analysis(
        workspace_id=1,
        url="https://business-os.example",
        draft={
            "businessName": "Business OS Test",
            "industry": "Local-first software",
            "contentPillars": ["Privacy", "Automation"],
        },
        field_origins={
            "businessName": "website",
            "industry": "ai-suggestion",
            "contentPillars": "website-suggestion",
        },
        sources=[{"url": "https://business-os.example", "title": "Business OS Test"}],
    )
    assert len(analysis["items"]) == 3

    knowledge = client.get("/api/workspaces/1/knowledge").json()
    business_name = next(item for item in knowledge["items"] if item["factKey"] == "businessName")
    assert business_name["status"] == "proposed"
    assert business_name["confidence"] == 90

    confirmed = client.patch(
        f"/api/workspaces/1/knowledge/items/{business_name['id']}",
        json={"status": "confirmed"},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["item"]["verifiedAt"]
    assert client.get("/api/state").json()["workspace"]["businessName"] == "Business OS Test"

    runtime = workspace_runtime()
    prompt = _generation_prompt(
        {"channel": "linkedin", "topic": "Privacy", "objective": "Awareness", "tone": "Direct"},
        runtime,
    )
    assert "Business OS Test" in prompt
    assert "Local-first software" not in prompt
    assert "Privacy\", \"Automation" not in prompt

    search = client.get("/api/workspaces/1/knowledge", params={"query": "Business"})
    assert search.status_code == 200
    assert any(item["id"] == business_name["id"] for item in search.json()["items"])


def test_generic_workflow_uses_one_terminal_approval(client) -> None:
    created = client.post(
        "/api/workflows",
        json={
            "name": "Business OS approval test",
            "kind": "content.repurpose",
            "approvalMode": "approval_required",
            "config": {"source": "knowledge"},
        },
    )
    assert created.status_code == 200
    workflow = created.json()["workflow"]

    started = client.post(
        f"/api/workflows/{workflow['id']}/runs",
        json={"trigger": "manual", "inputData": {"topic": "Local ownership"}},
    )
    assert started.status_code == 200
    run = started.json()["run"]
    assert run["status"] == "waiting_approval"
    approval_id = run["approval"]["id"]

    first = client.post(
        f"/api/approvals/{approval_id}/decision",
        json={"action": "approve", "source": "dashboard", "actor": "Test operator"},
    )
    assert first.status_code == 200
    assert first.json()["approval"]["status"] == "approved"

    duplicate = client.post(
        f"/api/approvals/{approval_id}/decision",
        json={"action": "approve", "source": "telegram", "actor": "Test operator"},
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["approval"]["duplicate"] is True


def test_dashboard_uses_real_counts_and_honest_analytics_state(client) -> None:
    response = client.get("/api/dashboard/summary")
    assert response.status_code == 200
    summary = response.json()["summary"]
    assert isinstance(summary["metrics"]["postsPublished"], int)
    assert isinstance(summary["metrics"]["leadsCaptured"], int)
    assert summary["engagement"]["available"] is False
    assert "Connect" in summary["engagement"]["reason"]
    assert len(summary["publishingTrend"]) == 30


def test_business_os_feature_contract_is_public(client) -> None:
    features = client.get("/api/state").json()["features"]
    assert features == {
        "edition": "business-os-v1.4",
        "labsEnabled": False,
        "previewModules": [],
        "businessOs": True,
        "knowledge": True,
        "unifiedInbox": True,
        "genericWorkflows": True,
    }


def test_content_generation_runs_as_a_progress_job_even_when_schedules_are_paused(
    client, monkeypatch
) -> None:
    from app.schemas import GeneratedContent

    async def fake_generate(*_args, **_kwargs):
        return GeneratedContent(
            title="Background content kit",
            body="A durable draft returned without blocking the browser request.",
            hashtags=["#Socium", "#LocalFirst"],
            call_to_action="Review the exact revision.",
            image_prompt="A private local business operating system",
            image_alt_text="Socium local business workspace",
            rationale="Exercises asynchronous progress and durable completion.",
        )

    monkeypatch.setattr("app.services.provider.generate_content", fake_generate)
    configured = client.put(
        "/api/settings/provider",
        json={
            "kind": "openai-compatible",
            "baseUrl": "https://provider.example/v1",
            "model": "background-test-model",
            "apiKey": "background-test-key",
        },
    )
    assert configured.status_code == 200
    assert client.put("/api/scheduler", json={"paused": True}).status_code == 200

    started = time.perf_counter()
    queued = client.post(
        "/api/posts/generations",
        json={
            "topic": "Durable background work",
            "channel": "linkedin",
            "tone": "Clear",
            "objective": "Prove immediate progress",
            "notifyTelegram": False,
            "notifySlack": False,
        },
    )
    assert queued.status_code == 202
    assert time.perf_counter() - started < 1
    job_id = queued.json()["job"]["id"]

    result = None
    for _ in range(100):
        result = client.get(f"/api/posts/generations/{job_id}")
        assert result.status_code == 200
        if result.json()["job"]["status"] in {"completed", "failed", "cancelled"}:
            break
        time.sleep(0.05)

    assert result is not None
    payload = result.json()
    assert payload["job"]["status"] == "completed"
    assert payload["job"]["progressPercent"] == 100
    assert payload["post"]["title"] == "Background content kit"
    assert payload["job"]["resultRef"] == payload["post"]["id"]
    assert client.put("/api/scheduler", json={"paused": False}).status_code == 200

    # This suite intentionally shares one application lifecycle; restore the
    # first-run provider state so legacy migration checks remain independent.
    from app.database import write_session
    from app.models import AppMetadata, LocalJob, Post, ProviderSettings

    with write_session() as session:
        session.delete(session.get(LocalJob, job_id))
        session.delete(session.get(Post, payload["post"]["id"]))
        provider = session.get(ProviderSettings, 1)
        provider.kind = "ollama"
        provider.base_url = "http://127.0.0.1:11434"
        provider.model = ""
        provider.api_key = None
        provider.updated_at = None
        for key in ("provider_verified_snapshot", "provider_verified_at"):
            metadata = session.get(AppMetadata, key)
            if metadata is not None:
                session.delete(metadata)
