from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest


def test_health_state_and_encrypted_settings(client) -> None:
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["mode"] == "local_only"
    assert health.json()["database"] == "sqlite"

    initial = client.get("/api/state")
    assert initial.status_code == 200
    assert initial.json()["runtime"]["database"] == "sqlite"
    assert initial.json()["features"] == {
        "edition": "social-v1",
        "labsEnabled": False,
        "previewModules": [],
    }

    workspace = client.put(
        "/api/settings/workspace",
        json={
            "name": "Test workspace",
            "businessName": "Example Studio",
            "description": "A local-first test business.",
            "timezone": "Asia/Karachi",
        },
    )
    assert workspace.status_code == 200
    assert workspace.json()["state"]["workspace"]["businessName"] == "Example Studio"

    provider = client.put(
        "/api/settings/provider",
        json={
            "kind": "openai-compatible",
            "baseUrl": "https://provider.example/v1",
            "model": "test-model",
            "apiKey": "do-not-store-in-plaintext",
        },
    )
    assert provider.status_code == 200
    assert provider.json()["state"]["provider"]["hasApiKey"] is True

    from app.config import get_settings

    database_path = Path(get_settings().database_path)
    with sqlite3.connect(database_path) as connection:
        encrypted = connection.execute("SELECT api_key FROM provider_settings WHERE id = 1").fetchone()[0]
    assert "do-not-store-in-plaintext" not in encrypted


def test_labs_require_an_explicit_environment_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import get_settings

    monkeypatch.setenv("SOCIUM_ENABLE_LABS", "1")
    get_settings.cache_clear()
    assert get_settings().labs_enabled is True

    monkeypatch.setenv("SOCIUM_ENABLE_LABS", "0")
    get_settings.cache_clear()
    assert get_settings().labs_enabled is False


def test_lead_import_deduplicates_tracks_evidence_and_honors_suppression(client) -> None:
    created = client.post(
        "/api/leads/import",
        json={
            "source": "csv",
            "rows": [
                {
                    "businessName": "Acme Studio",
                    "website": "https://www.acme.example/about",
                    "email": "HELLO@ACME.EXAMPLE",
                    "location": "Karachi",
                },
                {
                    "businessName": "Acme Studio",
                    "website": "acme.example",
                    "phone": "+92 300 1234567",
                    "location": "Karachi",
                },
            ],
        },
    )
    assert created.status_code == 200
    assert created.json()["result"] == {
        "processed": 2,
        "created": 1,
        "merged": 1,
        "unchanged": 0,
        "suppressed": 0,
    }

    merged = client.post(
        "/api/leads/import",
        json={
            "source": "linkedin-export",
            "rows": [
                {
                    "businessName": "Acme Studio",
                    "website": "acme.example",
                    "email": "hello@acme.example",
                    "phone": "+92 300 1234567",
                    "sourceRef": "https://www.linkedin.com/company/acme-studio",
                }
            ],
        },
    )
    assert merged.status_code == 200
    assert merged.json()["result"]["merged"] == 1

    leads = client.get("/api/leads?query=acme")
    assert leads.status_code == 200
    assert leads.json()["total"] == 1
    lead = leads.json()["items"][0]
    assert lead["phone"] == "+92 300 1234567"
    assert {item["source"] for item in lead["evidence"]} == {"csv", "linkedin-export"}

    qualified = client.patch(f"/api/leads/{lead['id']}", json={"status": "qualified"})
    assert qualified.status_code == 200
    assert qualified.json()["lead"]["status"] == "qualified"

    suppressed = client.post(
        f"/api/leads/{lead['id']}/suppress",
        json={"reason": "Contact opted out"},
    )
    assert suppressed.status_code == 200
    assert suppressed.json()["state"]["leadSummary"]["suppressed"] == 1

    blocked_reimport = client.post(
        "/api/leads/import",
        json={
            "source": "crm-export",
            "rows": [{"businessName": "Acme Studio", "email": "hello@acme.example"}],
        },
    )
    assert blocked_reimport.status_code == 200
    assert blocked_reimport.json()["result"]["suppressed"] == 1
    assert blocked_reimport.json()["result"]["created"] == 0

    restored = client.post(f"/api/leads/{lead['id']}/restore")
    assert restored.status_code == 200
    assert restored.json()["lead"]["suppressed"] is False
    assert restored.json()["lead"]["status"] == "qualified"


def test_google_places_connector_is_encrypted_and_search_results_are_transient(client, monkeypatch) -> None:
    from app.connectors.base import ConnectorTestResult

    api_key = "google-places-test-fixture"
    created = client.post(
        "/api/connectors",
        json={
            "adapterId": "google-places",
            "name": "Local discovery",
            "config": {"region_code": "PK", "language_code": "en"},
            "secrets": {"api_key": api_key},
            "scopes": ["places:search"],
            "enabled": True,
        },
    )
    assert created.status_code == 200
    account = created.json()["account"]
    assert account["secretStatus"] == {"api_key": True}
    assert api_key not in created.text

    from app.config import get_settings

    with sqlite3.connect(get_settings().database_path) as connection:
        encrypted = connection.execute(
            "SELECT encrypted_secrets FROM connector_accounts WHERE id = ?",
            (account["id"],),
        ).fetchone()[0]
    assert api_key not in encrypted

    async def fake_test(_self, config, secrets):
        assert config == {"region_code": "PK", "language_code": "en"}
        assert secrets == {"api_key": api_key}
        return ConnectorTestResult(
            ok=True,
            message="Google Places API key verified.",
            remote_account_id="places-api-new",
        )

    monkeypatch.setattr("app.connectors.google_places.GooglePlacesAdapter.test_connection", fake_test)
    tested = client.post(f"/api/connectors/{account['id']}/test")
    assert tested.status_code == 200

    async def fake_search(key, query, **options):
        assert key == api_key
        assert query == "dentists in Lahore"
        assert options["region_code"] == "PK"
        return [
            {
                "placeId": "place-123",
                "name": "Example Dental",
                "address": "Lahore, Pakistan",
                "website": "https://dental.example/",
                "phone": "+92 300 0000000",
                "googleMapsUri": "https://maps.google.com/?cid=123",
                "attributions": [],
            }
        ]

    monkeypatch.setattr("app.main.search_google_places", fake_search)
    discovered = client.post(
        "/api/leads/discover/google-places",
        json={"query": "dentists in Lahore", "pageSize": 10},
    )
    assert discovered.status_code == 200
    assert discovered.headers["cache-control"] == "no-store"
    assert discovered.json()["storagePolicy"] == "transient"
    assert discovered.json()["attribution"] == "Google Maps"
    assert discovered.json()["results"][0]["placeId"] == "place-123"
    assert client.get("/api/leads?query=Example%20Dental").json()["total"] == 0


def test_public_website_crawl_preview_and_import(client, monkeypatch) -> None:
    from app.errors import AppError
    from app.services.crawler import PageExtractor, validate_public_url

    extractor = PageExtractor()
    extractor.feed(
        """
        <html><head><title>Acme Studio | Home</title><meta name="description" content="Local studio">
        <script type="application/ld+json">{
          "@type":"LocalBusiness","name":"Acme Studio","telephone":"+92 300 1234567",
          "email":"hello@acme.example","address":{"addressLocality":"Karachi","addressCountry":"PK"}
        }</script></head><body><a href="/contact">Contact</a><h1>Acme Studio</h1></body></html>
        """
    )
    extracted = extractor.result()
    assert extracted["businessNames"] == ["Acme Studio"]
    assert extracted["emails"] == ["hello@acme.example"]
    assert extracted["phones"] == ["+92 300 1234567"]
    assert extracted["locations"] == ["Karachi, PK"]

    with pytest.raises(AppError, match="public internet addresses"):
        asyncio.run(validate_public_url("http://127.0.0.1/private"))

    async def fake_crawl(url: str):
        assert url == "https://acme.example"
        return {
            "businessName": "Acme Studio",
            "website": "https://acme.example/",
            "email": "hello@acme.example",
            "phone": "+92 300 1234567",
            "location": "Karachi, PK",
            "sourceRef": "https://acme.example/",
            "notes": "Local studio",
            "pages": [
                {"url": "https://acme.example/", "title": "Acme Studio"},
                {"url": "https://acme.example/contact", "title": "Contact"},
            ],
            "robotsRespected": True,
            "userAgent": "Socium/0.9",
        }

    monkeypatch.setattr("app.main.crawl_website", fake_crawl)
    preview = client.post("/api/leads/crawl", json={"url": "https://acme.example"})
    assert preview.status_code == 200
    assert preview.headers["cache-control"] == "no-store"
    assert preview.json()["result"]["robotsRespected"] is True

    imported = client.post(
        "/api/leads/import",
        json={"source": "website-crawl", "rows": [preview.json()["result"]]},
    )
    assert imported.status_code == 200
    lead = client.get("/api/leads?query=acme.example").json()["items"][0]
    assert "website-crawl" in {item["source"] for item in lead["evidence"]}
    website_evidence = next(item for item in lead["evidence"] if item["source"] == "website-crawl")
    assert website_evidence["sourceLabel"] == "Public website crawl"


def test_deterministic_seo_analyzer_scores_real_page_signals() -> None:
    from app.services.seo_audit import analyze_seo_document

    body_copy = " ".join(["Useful local service information for customers and search visitors."] * 55)
    html = f"""
    <!doctype html>
    <html lang="en"><head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>Karachi Website Performance and SEO Reviews</title>
      <meta name="description" content="A practical website performance and local SEO review for Karachi businesses, with clear evidence and prioritized recommendations.">
      <link rel="canonical" href="https://audit.example/">
      <meta property="og:title" content="Karachi Website Reviews">
      <meta property="og:description" content="Clear and evidence-based website review.">
      <meta property="og:image" content="https://audit.example/share.jpg">
      <script type="application/ld+json">{{"@type":"ProfessionalService","name":"Audit Studio"}}</script>
    </head><body>
      <h1>Website performance and SEO reviews</h1><h2>What the review covers</h2>
      <p>{body_copy}</p><img src="report.jpg" alt="Example audit report">
      <a href="/services">Services</a><a href="/work">Work</a><a href="/about">About</a><a href="/contact">Contact</a>
    </body></html>
    """
    result = analyze_seo_document(
        requested_url="https://audit.example/",
        final_url="https://audit.example/",
        status_code=200,
        content_type="text/html",
        headers={"content-type": "text/html; charset=utf-8"},
        content=html.encode(),
        duration_ms=240,
        robots_respected=True,
    )
    assert result["overallScore"] >= 90
    assert result["scores"]["technical"] >= 90
    assert result["metrics"]["wordCount"] >= 300
    assert result["metrics"]["imagesMissingAlt"] == 0
    assert result["metrics"]["structuredDataTypes"] == ["ProfessionalService"]
    assert all(item["status"] == "passed" for item in result["checks"])


def test_persisted_seo_audits_and_restart_safe_schedule(client, monkeypatch) -> None:
    from app.database import write_session
    from app.models import LocalJob
    from app.scheduler import LocalScheduler
    from app.services.seo_audit import analyze_seo_document

    def result_for(url: str, score_variant: int = 0):
        description = (
            "A concise, evidence-based local SEO audit description for business owners and website teams."
        )
        html = f"""
        <html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
        <title>Local SEO audit snapshot for example businesses</title>
        <meta name="description" content="{description}"><link rel="canonical" href="{url}">
        </head><body><h1>Local SEO audit</h1><h2>Evidence</h2><p>{"useful evidence " * (25 + score_variant)}</p>
        <a href="/one">One</a><a href="/two">Two</a><a href="/three">Three</a></body></html>
        """
        return analyze_seo_document(
            requested_url=url,
            final_url=url,
            status_code=200,
            content_type="text/html",
            headers={"content-type": "text/html; charset=utf-8"},
            content=html.encode(),
            duration_ms=300,
            robots_respected=True,
        )

    async def fake_audit(url: str):
        assert url == "https://seo-audit.example/"
        return result_for(url)

    monkeypatch.setattr("app.main.audit_website", fake_audit)
    created = client.post("/api/seo/audits", json={"url": "https://seo-audit.example/"})
    assert created.status_code == 200
    snapshot = created.json()["audit"]
    assert snapshot["trigger"] == "manual"
    assert snapshot["previousScore"] is None
    assert "content" not in snapshot
    assert "html" not in snapshot

    history = client.get("/api/seo/audits")
    assert history.status_code == 200
    assert history.headers["cache-control"] == "no-store"
    assert history.json()["items"][0]["id"] == snapshot["id"]
    assert history.json()["summary"]["sites"] >= 1
    assert client.get(f"/api/seo/audits/{snapshot['id']}").status_code == 200

    run_at = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
    scheduled = client.post(
        "/api/seo/jobs",
        json={"url": "https://seo-audit.example/", "runAt": run_at},
    )
    assert scheduled.status_code == 200
    assert scheduled.json()["created"] is True
    duplicate = client.post(
        "/api/seo/jobs",
        json={"url": "https://seo-audit.example/", "runAt": run_at},
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["created"] is False
    job_id = scheduled.json()["job"]["id"]

    async def fake_scheduled_audit(url: str):
        return result_for(url, score_variant=10)

    monkeypatch.setattr("app.scheduler.audit_website", fake_scheduled_audit)
    with write_session() as session:
        job = session.get(LocalJob, job_id)
        assert job is not None
        job.status = "running"
        job.attempts = 1
        job.locked_at = datetime.now(UTC).isoformat()
    worker = LocalScheduler(interval=1, catch_up_hours=24, stale_minutes=10)
    asyncio.run(worker._execute(scheduled.json()["job"]))

    jobs = client.get("/api/seo/jobs").json()["items"]
    completed = next(item for item in jobs if item["id"] == job_id)
    assert completed["status"] == "completed"
    latest = client.get("/api/seo/audits").json()["items"][0]
    assert latest["trigger"] == "scheduled"
    assert latest["previousScore"] is not None
    assert all(job["kind"] == "post.publish" for job in client.get("/api/state").json()["jobs"])

    cancel_at = (datetime.now(UTC) + timedelta(hours=3)).isoformat()
    cancel_job = client.post(
        "/api/seo/jobs",
        json={"url": "https://cancel-audit.example/", "runAt": cancel_at},
    ).json()["job"]
    cancelled = client.post(f"/api/seo/jobs/{cancel_job['id']}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["job"]["status"] == "cancelled"


def test_deterministic_icp_scoring_high_intent_filter_and_manual_correction(client) -> None:
    invalid = client.put(
        "/api/leads/icp-profile",
        json={"name": "Empty ICP", "targetKeywords": [], "targetLocations": []},
    )
    assert invalid.status_code == 422

    saved = client.put(
        "/api/leads/icp-profile",
        json={
            "name": "Lahore dental practices",
            "targetKeywords": ["dental"],
            "excludedKeywords": ["university"],
            "targetLocations": ["Lahore"],
            "requireWebsite": True,
            "requireContact": True,
        },
    )
    assert saved.status_code == 200
    assert saved.json()["rescored"] >= 1
    assert saved.json()["profile"]["version"] == 1

    imported = client.post(
        "/api/leads/import",
        json={
            "source": "manual",
            "rows": [
                {
                    "businessName": "Northstar Dental Practice",
                    "website": "https://northstar-dental.example",
                    "email": "hello@northstar-dental.example",
                    "location": "Lahore, Pakistan",
                },
                {
                    "businessName": "Northstar Dental University",
                    "website": "https://northstar-university.example",
                    "email": "office@northstar-university.example",
                    "location": "Lahore, Pakistan",
                },
            ],
        },
    )
    assert imported.status_code == 200
    records = client.get("/api/leads?query=Northstar").json()["items"]
    practice = next(item for item in records if "Practice" in item["businessName"])
    university = next(item for item in records if "University" in item["businessName"])
    assert practice["icpScore"] == 100
    assert practice["effectiveScore"] == 100
    assert sum(reason["points"] for reason in practice["icpReasons"]) == 100
    assert {reason["code"] for reason in practice["icpReasons"]} >= {
        "target_keyword_match",
        "target_location_match",
        "public_website",
        "direct_contact",
    }
    assert university["icpScore"] == 65
    assert "excluded_keyword_match" in {reason["code"] for reason in university["icpReasons"]}

    high_intent = client.get("/api/leads?status=high-intent&query=Northstar").json()
    assert [item["id"] for item in high_intent["items"]] == [practice["id"]]

    corrected = client.put(
        f"/api/leads/{university['id']}/score-override",
        json={"score": 88, "reason": "Verified multi-location commercial clinic."},
    )
    assert corrected.status_code == 200
    assert corrected.json()["lead"]["icpScore"] == 65
    assert corrected.json()["lead"]["effectiveScore"] == 88
    assert corrected.json()["state"]["leadSummary"]["highIntent"] >= 2

    rescored = client.put(
        "/api/leads/icp-profile",
        json={
            "name": "Lahore dental practices",
            "targetKeywords": ["dental"],
            "excludedKeywords": ["university"],
            "targetLocations": ["Lahore"],
            "requireWebsite": True,
            "requireContact": True,
        },
    )
    assert rescored.status_code == 200
    refreshed = client.get("/api/leads?query=Northstar%20Dental%20University").json()["items"][0]
    assert refreshed["icpProfileVersion"] == 2
    assert refreshed["icpScore"] == 65
    assert refreshed["effectiveScore"] == 88

    cleared = client.delete(f"/api/leads/{university['id']}/score-override")
    assert cleared.status_code == 200
    assert cleared.json()["lead"]["manualScore"] is None
    assert cleared.json()["lead"]["effectiveScore"] == 65


def test_reviewed_outreach_export_and_explicit_retention_delete(client, monkeypatch) -> None:
    from app.schemas import GeneratedOutreach

    provider = client.put(
        "/api/settings/provider",
        json={
            "kind": "openai-compatible",
            "baseUrl": "https://provider.example/v1",
            "model": "outreach-test-model",
            "apiKey": "",
        },
    )
    assert provider.status_code == 200

    imported = client.post(
        "/api/leads/import",
        json={
            "source": "manual",
            "rows": [
                {
                    "businessName": "Reviewed Outreach Pilot",
                    "website": "https://reviewed-outreach.example",
                    "email": "owner@reviewed-outreach.example",
                    "location": "Karachi, Pakistan",
                    "notes": "Publicly listed independent design studio.",
                }
            ],
        },
    )
    assert imported.status_code == 200
    lead = client.get("/api/leads?query=Reviewed%20Outreach%20Pilot").json()["items"][0]
    assert lead["outreachReady"] is False
    assert "Record a legal basis." in lead["outreachBlockers"]

    incompatible = client.put(
        f"/api/leads/{lead['id']}/compliance",
        json={
            "consentStatus": "not_applicable",
            "legalBasis": "consent",
            "legalBasisNote": "The owner asked to receive a proposal.",
            "retentionUntil": "2030-12-31",
        },
    )
    assert incompatible.status_code == 400

    withdrawn = client.put(
        f"/api/leads/{lead['id']}/compliance",
        json={
            "consentStatus": "withdrawn",
            "legalBasis": "consent",
            "legalBasisNote": "The contact withdrew permission; outreach must remain blocked.",
            "retentionUntil": "2030-12-31",
        },
    )
    assert withdrawn.status_code == 200
    assert withdrawn.json()["lead"]["outreachReady"] is False
    assert "Consent was withdrawn." in withdrawn.json()["lead"]["outreachBlockers"]

    reviewed = client.put(
        f"/api/leads/{lead['id']}/compliance",
        json={
            "consentStatus": "granted",
            "legalBasis": "consent",
            "legalBasisNote": "The owner asked to receive a one-time proposal by email.",
            "retentionUntil": "2030-12-31",
        },
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["lead"]["outreachReady"] is True
    ready_ids = {item["id"] for item in client.get("/api/leads?status=outreach-ready").json()["items"]}
    assert lead["id"] in ready_ids

    async def fake_generate_outreach(*_args, **_kwargs):
        return GeneratedOutreach(
            subject="A local collaboration idea",
            body="Hello,\n\nHere is a concise proposal for your review.\n\nRegards,\nExample Studio",
            rationale="Uses the verified public business context without invented familiarity.",
        )

    monkeypatch.setattr("app.main.generate_outreach", fake_generate_outreach)
    generated = client.post(
        f"/api/leads/{lead['id']}/outreach-drafts",
        json={
            "objective": "Offer a one-time website performance review",
            "tone": "Clear and respectful",
        },
    )
    assert generated.status_code == 200
    draft = generated.json()["draft"]
    assert draft["revision"] == 1
    assert draft["status"] == "draft"

    unapproved_export = client.post(f"/api/outreach-drafts/{draft['id']}/export", json={"revision": 1})
    assert unapproved_export.status_code == 400

    edited = client.put(
        f"/api/outreach-drafts/{draft['id']}",
        json={
            "subject": "A reviewed local collaboration idea",
            "body": "Hello,\n\nThis edited proposal still needs approval.\n\nRegards,\nExample Studio",
        },
    )
    assert edited.status_code == 200
    assert edited.json()["draft"]["revision"] == 2

    stale = client.post(
        f"/api/outreach-drafts/{draft['id']}/decision",
        json={"decision": "approve", "revision": 1},
    )
    assert stale.status_code == 400
    approved = client.post(
        f"/api/outreach-drafts/{draft['id']}/decision",
        json={"decision": "approve", "revision": 2},
    )
    assert approved.status_code == 200

    exported = client.post(f"/api/outreach-drafts/{draft['id']}/export", json={"revision": 2})
    assert exported.status_code == 200
    assert exported.json()["mimeType"].startswith("text/csv")
    assert "owner@reviewed-outreach.example" in exported.json()["content"]
    assert exported.json()["draft"]["status"] == "exported"

    data_export = client.post(f"/api/leads/{lead['id']}/data-export")
    assert data_export.status_code == 200
    exported_data = json.loads(data_export.json()["content"])
    assert exported_data["lead"]["id"] == lead["id"]
    assert exported_data["outreachDrafts"][0]["revision"] == 2

    expired = client.put(
        f"/api/leads/{lead['id']}/compliance",
        json={
            "consentStatus": "granted",
            "legalBasis": "consent",
            "legalBasisNote": "Retention review date intentionally expired for operator review.",
            "retentionUntil": "2020-01-01",
        },
    )
    assert expired.status_code == 200
    assert expired.json()["lead"]["retentionExpired"] is True
    expired_ids = {item["id"] for item in client.get("/api/leads?status=retention-expired").json()["items"]}
    assert lead["id"] in expired_ids

    wrong_confirmation = client.request(
        "DELETE",
        f"/api/leads/{lead['id']}",
        json={"reason": "Retention period ended.", "confirmation": "REMOVE"},
    )
    assert wrong_confirmation.status_code == 422
    deleted = client.request(
        "DELETE",
        f"/api/leads/{lead['id']}",
        json={"reason": "Retention period ended.", "confirmation": "DELETE"},
    )
    assert deleted.status_code == 200
    assert deleted.json()["deletedId"] == lead["id"]
    assert client.get("/api/leads?query=Reviewed%20Outreach%20Pilot").json()["total"] == 0
    assert any(event["action"] == "lead.data_deleted" for event in deleted.json()["state"]["audit"])


def test_draft_version_approval_and_single_publish(client, monkeypatch) -> None:
    from app.schemas import GeneratedContent

    async def fake_generate(*_args, **_kwargs):
        return GeneratedContent(
            title="Local launch",
            body="A factual post generated for review.",
            hashtags=["#local"],
            rationale="Tests the approval-first content path.",
        )

    async def fake_publish(*_args, **_kwargs):
        return "telegram-message-42"

    monkeypatch.setattr("app.main.generate_content", fake_generate)
    monkeypatch.setattr("app.services.publishing.publish_telegram_post", fake_publish)

    generated = client.post(
        "/api/posts/generate",
        json={
            "topic": "Local launch",
            "channel": "telegram",
            "tone": "Clear",
            "objective": "Explain the release",
            "notifyTelegram": False,
        },
    )
    assert generated.status_code == 200
    post = generated.json()["post"]
    assert post["revision"] == 1
    assert post["status"] == "pending"

    approved = client.post(
        f"/api/posts/{post['id']}/decision",
        json={"decision": "approve", "revision": 1},
    )
    assert approved.status_code == 200

    edited = client.patch(
        f"/api/posts/{post['id']}",
        json={"title": "Revised launch", "body": "Revised factual copy.", "hashtags": ["local"]},
    )
    assert edited.status_code == 200
    revised = next(item for item in edited.json()["state"]["posts"] if item["id"] == post["id"])
    assert revised["revision"] == 2
    assert revised["status"] == "pending"

    stale = client.post(
        f"/api/posts/{post['id']}/decision",
        json={"decision": "approve", "revision": 1},
    )
    assert stale.status_code == 400

    approved_again = client.post(
        f"/api/posts/{post['id']}/decision",
        json={"decision": "approve", "revision": 2},
    )
    assert approved_again.status_code == 200

    telegram = client.put(
        "/api/settings/telegram",
        json={"chatId": "12345", "botToken": "123456:test-token"},
    )
    assert telegram.status_code == 200

    published = client.post(f"/api/posts/{post['id']}/publish", json={"revision": 2})
    assert published.status_code == 200
    final_post = next(item for item in published.json()["state"]["posts"] if item["id"] == post["id"])
    assert final_post["status"] == "published"
    assert final_post["remoteId"] == "telegram-message-42"

    duplicate = client.post(f"/api/posts/{post['id']}/publish", json={"revision": 2})
    assert duplicate.status_code == 400


def test_local_telegram_polling_mode(client, monkeypatch) -> None:
    async def fake_connection(_token: str):
        return {"id": 1, "name": "@local_test_bot"}

    async def fake_delete(_token: str):
        return None

    async def fake_updates(*_args, **_kwargs):
        await asyncio.sleep(0.05)
        return []

    monkeypatch.setattr("app.main.test_connection", fake_connection)
    monkeypatch.setattr("app.main.delete_webhook", fake_delete)
    monkeypatch.setattr("app.poller.get_updates", fake_updates)

    started = client.put("/api/integrations/telegram/polling", json={"enabled": True})
    assert started.status_code == 200
    assert started.json()["state"]["telegram"]["pollingEnabled"] is True

    stopped = client.put("/api/integrations/telegram/polling", json={"enabled": False})
    assert stopped.status_code == 200
    assert stopped.json()["state"]["telegram"]["pollingEnabled"] is False


def test_durable_scheduler_is_idempotent_and_publishes_after_resume(client, monkeypatch) -> None:
    from app.schemas import GeneratedContent

    sequence = 0

    async def fake_generate(*_args, **_kwargs):
        nonlocal sequence
        sequence += 1
        return GeneratedContent(
            title=f"Scheduled draft {sequence}",
            body="A revision-bound scheduled post.",
            hashtags=["#scheduler"],
            rationale="Exercises durable local scheduling.",
        )

    async def fake_publish(*_args, **_kwargs):
        return "scheduled-message-99"

    monkeypatch.setattr("app.main.generate_content", fake_generate)
    monkeypatch.setattr("app.services.publishing.publish_telegram_post", fake_publish)

    telegram = client.put(
        "/api/settings/telegram",
        json={"chatId": "12345", "botToken": "123456:scheduler-token"},
    )
    assert telegram.status_code == 200

    paused = client.put("/api/scheduler", json={"paused": True})
    assert paused.status_code == 200
    assert paused.json()["state"]["scheduler"]["paused"] is True

    def approved_post(topic: str) -> dict:
        generated = client.post(
            "/api/posts/generate",
            json={
                "topic": topic,
                "channel": "telegram",
                "tone": "Clear",
                "objective": "Test durable scheduling",
                "notifyTelegram": False,
            },
        ).json()["post"]
        decision = client.post(
            f"/api/posts/{generated['id']}/decision",
            json={"decision": "approve", "revision": generated["revision"]},
        )
        assert decision.status_code == 200
        return generated

    cancellable = approved_post("Schedule once")
    future = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()
    first = client.post(
        f"/api/posts/{cancellable['id']}/schedule",
        json={"revision": cancellable["revision"], "runAt": future},
    )
    duplicate = client.post(
        f"/api/posts/{cancellable['id']}/schedule",
        json={"revision": cancellable["revision"], "runAt": future},
    )
    assert first.status_code == 200
    assert first.json()["created"] is True
    assert duplicate.status_code == 200
    assert duplicate.json()["created"] is False
    assert duplicate.json()["job"]["id"] == first.json()["job"]["id"]

    cancelled = client.post(f"/api/jobs/{first.json()['job']['id']}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["job"]["status"] == "cancelled"

    due = approved_post("Run after resume")
    scheduled = client.post(
        f"/api/posts/{due['id']}/schedule",
        json={"revision": due["revision"], "runAt": (datetime.now(UTC) - timedelta(seconds=1)).isoformat()},
    )
    assert scheduled.status_code == 200
    assert scheduled.json()["job"]["status"] == "queued"

    resumed = client.put("/api/scheduler", json={"paused": False})
    assert resumed.status_code == 200

    deadline = time.monotonic() + 3
    final_state = resumed.json()["state"]
    while time.monotonic() < deadline:
        final_state = client.get("/api/state").json()
        final_post = next(post for post in final_state["posts"] if post["id"] == due["id"])
        if final_post["status"] == "published":
            break
        time.sleep(0.05)

    final_post = next(post for post in final_state["posts"] if post["id"] == due["id"])
    final_job = next(job for job in final_state["jobs"] if job["id"] == scheduled.json()["job"]["id"])
    assert final_post["status"] == "published"
    assert final_post["remoteId"] == "scheduled-message-99"
    assert final_job["status"] == "completed"
    assert final_job["attempts"] == 1


def test_slack_approval_message_buttons_are_revision_bound(monkeypatch) -> None:
    captured: dict = {}

    async def fake_request(_token: str, method: str, body: dict, **_kwargs):
        captured["method"] = method
        captured["body"] = body
        return {"ok": True, "ts": "1712345678.000200"}

    monkeypatch.setattr("app.services.slack.slack_request", fake_request)
    from app.services.slack import send_approval_message

    message_ts = asyncio.run(
        send_approval_message(
            "xoxb-test",
            "C1234567890",
            {
                "id": "post-123",
                "revision": 7,
                "channel": "linkedin",
                "title": "A safe review title",
                "body": "Review this exact content.",
                "hashtags": ["#local"],
            },
        )
    )
    assert message_ts == "1712345678.000200"
    assert captured["method"] == "chat.postMessage"
    assert captured["body"]["channel"] == "C1234567890"
    actions = captured["body"]["blocks"][-1]["elements"]
    assert actions[0]["value"] == "lg:approve:post-123:7"
    assert actions[1]["value"] == "lg:reject:post-123:7"


def test_connector_vault_redacts_secrets_and_validates_slack(client, monkeypatch) -> None:
    from app.connectors.base import ConnectorTestResult
    from app.schemas import GeneratedContent

    catalog = client.get("/api/connectors")
    assert catalog.status_code == 200
    slack_manifest = next(item for item in catalog.json()["catalog"] if item["adapterId"] == "slack")
    assert slack_manifest["availability"] == "available"
    assert set(slack_manifest["requiredScopes"]) == {"chat:write", "connections:write"}
    approval_adapters = {
        item["adapterId"] for item in catalog.json()["catalog"] if "approval" in item["capabilities"]
    }
    assert approval_adapters == {"telegram", "slack"}
    assert all(item["adapterId"] != "whatsapp" for item in catalog.json()["catalog"])

    removed_connector = client.post(
        "/api/connectors",
        json={
            "adapterId": "whatsapp",
            "name": "Removed approval transport",
            "config": {},
            "secrets": {},
            "scopes": [],
            "enabled": True,
        },
    )
    assert removed_connector.status_code == 404
    assert removed_connector.json()["error"] == "Unknown connector adapter."

    removed_generation_option = client.post(
        "/api/posts/generate",
        json={
            "topic": "Removed approval transport",
            "channel": "linkedin",
            "notifyTelegram": False,
            "notifyWhatsapp": True,
        },
    )
    assert removed_generation_option.status_code == 422

    invalid = client.post(
        "/api/connectors",
        json={
            "adapterId": "slack",
            "name": "Missing scope",
            "config": {"approval_channel_id": "C0123456789"},
            "secrets": {"bot_token": "xoxb-invalid", "app_token": "xapp-invalid"},
            "scopes": ["chat:write"],
        },
    )
    assert invalid.status_code == 400
    assert "connections:write" in invalid.json()["error"]

    bot_token = "xoxb-local-test-fixture"
    app_token = "xapp-local-test-fixture"
    created = client.post(
        "/api/connectors",
        json={
            "adapterId": "slack",
            "name": "Approvals workspace",
            "config": {"approval_channel_id": "C0123456789"},
            "secrets": {"bot_token": bot_token, "app_token": app_token},
            "scopes": ["chat:write", "connections:write"],
            "enabled": True,
        },
    )
    assert created.status_code == 200
    account = created.json()["account"]
    account_id = account["id"]
    assert account["secretStatus"] == {"bot_token": True, "app_token": True}
    assert bot_token not in created.text
    assert app_token not in created.text

    from app.config import get_settings

    with sqlite3.connect(get_settings().database_path) as connection:
        encrypted = connection.execute(
            "SELECT encrypted_secrets FROM connector_accounts WHERE id = ?",
            (account_id,),
        ).fetchone()[0]
    assert bot_token not in encrypted
    assert app_token not in encrypted

    updated = client.put(
        f"/api/connectors/{account_id}",
        json={
            "adapterId": "slack",
            "name": "Approvals workspace",
            "config": {"approval_channel_id": "C9876543210"},
            "secrets": {},
            "scopes": ["chat:write", "connections:write"],
            "enabled": True,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["account"]["secretStatus"] == {"bot_token": True, "app_token": True}

    async def fake_slack_test(_self, config, secrets):
        assert config["approval_channel_id"] == "C9876543210"
        assert secrets == {"bot_token": bot_token, "app_token": app_token}
        return ConnectorTestResult(
            ok=True,
            message="Connected to Slack workspace Test team.",
            remote_account_id="T123456",
            details={"team": "Test team", "socketMode": "ready"},
        )

    monkeypatch.setattr("app.connectors.slack.SlackAdapter.test_connection", fake_slack_test)
    tested = client.post(f"/api/connectors/{account_id}/test")
    assert tested.status_code == 200
    assert tested.json()["remoteAccountId"] == "T123456"
    verified = next(
        item for item in tested.json()["state"]["connectors"]["accounts"] if item["id"] == account_id
    )
    assert verified["status"] == "verified"
    assert verified["listener"] == {"active": False, "status": "stopped", "lastError": None}

    provider = client.put(
        "/api/settings/provider",
        json={
            "kind": "openai-compatible",
            "baseUrl": "https://provider.example/v1",
            "model": "test-model",
            "apiKey": "provider-test-key",
        },
    )
    assert provider.status_code == 200

    async def fake_generate(*_args, **_kwargs):
        return GeneratedContent(
            title="Slack review",
            body="A revision-bound Slack approval draft.",
            hashtags=["#slack"],
            rationale="Exercises Socket Mode approval rules.",
        )

    sent_posts: list[dict] = []

    async def fake_slack_send(_token: str, channel_id: str, post: dict):
        assert channel_id == "C9876543210"
        sent_posts.append(post)
        return "1712345678.000100"

    monkeypatch.setattr("app.main.generate_content", fake_generate)
    monkeypatch.setattr("app.connectors.service.send_approval_message", fake_slack_send)
    generated = client.post(
        "/api/posts/generate",
        json={
            "topic": "Slack workflow",
            "channel": "linkedin",
            "tone": "Clear",
            "objective": "Review the workflow",
            "notifyTelegram": False,
            "notifySlack": True,
        },
    )
    assert generated.status_code == 200
    post = generated.json()["post"]
    assert generated.json()["notifications"] == [
        {"channel": "slack", "ok": True, "message": "Approval request sent to Slack."}
    ]
    assert sent_posts[0]["id"] == post["id"]

    resent = client.post(
        f"/api/posts/{post['id']}/approvals/slack",
        json={"revision": post["revision"]},
    )
    assert resent.status_code == 200
    assert resent.json()["delivery"]["messageTs"] == "1712345678.000100"

    from app.slack_listener import process_slack_interaction

    interaction = {
        "type": "block_actions",
        "channel": {"id": "C0000000000"},
        "user": {"id": "U123456"},
        "actions": [
            {
                "action_id": "socium_approve",
                "value": f"lg:approve:{post['id']}:{post['revision']}",
            }
        ],
    }
    unauthorized = process_slack_interaction(interaction, "C9876543210")
    assert unauthorized is not None
    assert "not authorized" in unauthorized.message
    pending = next(item for item in client.get("/api/state").json()["posts"] if item["id"] == post["id"])
    assert pending["status"] == "pending"

    interaction["channel"] = {"id": "C9876543210"}

    class FakeSocket:
        def __init__(self) -> None:
            self.sent: list[str] = []

        async def send(self, message: str) -> None:
            self.sent.append(message)

    socket = FakeSocket()
    feedback: list[str] = []

    async def fake_feedback(_token: str, _channel: str, _user: str, message: str) -> None:
        assert socket.sent == ['{"envelope_id": "env-1"}']
        feedback.append(message)

    monkeypatch.setattr("app.slack_listener.send_decision_feedback", fake_feedback)
    from app.slack_listener import SlackSocketListener

    listener = SlackSocketListener(enabled=False)
    reconnect = asyncio.run(
        listener._handle_envelope(
            socket,  # type: ignore[arg-type]
            json.dumps(
                {
                    "envelope_id": "env-1",
                    "type": "interactive",
                    "payload": interaction,
                }
            ),
            bot_token,
            "C9876543210",
            account_id,
        )
    )
    assert reconnect is False
    assert feedback == ["Revision 1 approved and locked."]
    approved = next(item for item in client.get("/api/state").json()["posts"] if item["id"] == post["id"])
    assert approved["status"] == "approved"
    repeated = process_slack_interaction(interaction, "C9876543210")
    assert repeated is not None
    assert "Current status: approved" in repeated.message
    assert any(event["action"] == "post.approved.slack" for event in client.get("/api/state").json()["audit"])

    removed = client.delete(f"/api/connectors/{account_id}")
    assert removed.status_code == 200
    assert all(item["id"] != account_id for item in removed.json()["state"]["connectors"]["accounts"])


def test_wordpress_connector_publishes_exact_approved_blog_revision(client, monkeypatch) -> None:
    from app.connectors.base import ConnectorTestResult
    from app.schemas import GeneratedContent
    from app.services.wordpress import WordPressPublishResult

    catalog = client.get("/api/connectors").json()["catalog"]
    manifest = next(item for item in catalog if item["adapterId"] == "wordpress")
    assert manifest["availability"] == "available"
    assert manifest["capabilities"] == ["publish", "cms"]
    assert manifest["requiredScopes"] == ["posts:write"]

    username = "editor"
    application_password = "abcd efgh ijkl mnop qrst uvwx"
    created = client.post(
        "/api/connectors",
        json={
            "adapterId": "wordpress",
            "name": "Company blog",
            "config": {"site_url": "https://example.com"},
            "secrets": {
                "username": username,
                "application_password": application_password,
            },
            "scopes": ["posts:write"],
            "enabled": True,
        },
    )
    assert created.status_code == 200
    account_id = created.json()["account"]["id"]
    assert username not in created.text
    assert application_password not in created.text

    async def fake_wordpress_test(_self, config, secrets):
        assert config == {"site_url": "https://example.com"}
        assert secrets == {"username": username, "application_password": application_password}
        return ConnectorTestResult(
            ok=True,
            message="Connected to WordPress as Example Editor.",
            remote_account_id="7",
            details={"site": "https://example.com", "user": "Example Editor"},
        )

    monkeypatch.setattr(
        "app.connectors.wordpress.WordPressAdapter.test_connection",
        fake_wordpress_test,
    )
    tested = client.post(f"/api/connectors/{account_id}/test")
    assert tested.status_code == 200
    assert tested.json()["remoteAccountId"] == "7"

    async def fake_generate(*_args, **_kwargs):
        return GeneratedContent(
            title="Approved WordPress title",
            body="First approved paragraph.\n\nSecond approved paragraph.",
            hashtags=["#local", "#growth"],
            rationale="Exercises the official WordPress publisher.",
        )

    delivered: list[dict] = []

    async def fake_wordpress_publish(site_url, saved_username, saved_password, post):
        assert site_url == "https://example.com"
        assert saved_username == username
        assert saved_password == application_password
        delivered.append(post)
        return WordPressPublishResult(
            remote_id="314",
            remote_url="https://example.com/approved-wordpress-title/",
        )

    monkeypatch.setattr("app.main.generate_content", fake_generate)
    monkeypatch.setattr("app.services.publishing.publish_wordpress_post", fake_wordpress_publish)
    generated = client.post(
        "/api/posts/generate",
        json={
            "topic": "WordPress launch",
            "channel": "blog",
            "tone": "Clear",
            "objective": "Publish the approved article",
            "notifyTelegram": False,
        },
    )
    assert generated.status_code == 200
    post = generated.json()["post"]
    approved = client.post(
        f"/api/posts/{post['id']}/decision",
        json={"decision": "approve", "revision": post["revision"]},
    )
    assert approved.status_code == 200

    published = client.post(
        f"/api/posts/{post['id']}/publish",
        json={"revision": post["revision"]},
    )
    assert published.status_code == 200
    final_post = next(item for item in published.json()["state"]["posts"] if item["id"] == post["id"])
    assert final_post["status"] == "published"
    assert final_post["remoteId"] == "314"
    assert final_post["remoteUrl"] == "https://example.com/approved-wordpress-title/"
    assert len(delivered) == 1
    assert delivered[0]["revision"] == post["revision"]
    assert delivered[0]["title"] == post["title"]
    assert delivered[0]["body"] == post["body"]
    assert delivered[0]["hashtags"] == post["hashtags"]

    duplicate = client.post(
        f"/api/posts/{post['id']}/publish",
        json={"revision": post["revision"]},
    )
    assert duplicate.status_code == 400

    client.put("/api/scheduler", json={"paused": True})
    scheduled_post = client.post(
        "/api/posts/generate",
        json={
            "topic": "Scheduled WordPress article",
            "channel": "blog",
            "tone": "Clear",
            "objective": "Verify the WordPress scheduler dispatch",
            "notifyTelegram": False,
        },
    ).json()["post"]
    client.post(
        f"/api/posts/{scheduled_post['id']}/decision",
        json={"decision": "approve", "revision": scheduled_post["revision"]},
    )
    scheduled = client.post(
        f"/api/posts/{scheduled_post['id']}/schedule",
        json={
            "revision": scheduled_post["revision"],
            "runAt": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
        },
    )
    assert scheduled.status_code == 200
    client.put("/api/scheduler", json={"paused": False})

    deadline = time.monotonic() + 3
    scheduled_state = client.get("/api/state").json()
    while time.monotonic() < deadline:
        scheduled_state = client.get("/api/state").json()
        current = next(item for item in scheduled_state["posts"] if item["id"] == scheduled_post["id"])
        if current["status"] == "published":
            break
        time.sleep(0.05)
    current = next(item for item in scheduled_state["posts"] if item["id"] == scheduled_post["id"])
    job = next(item for item in scheduled_state["jobs"] if item["id"] == scheduled.json()["job"]["id"])
    assert current["status"] == "published"
    assert current["remoteUrl"] == "https://example.com/approved-wordpress-title/"
    assert job["status"] == "completed"
    assert len(delivered) == 2


def test_wordpress_payload_is_safe_and_remote_sites_require_https(monkeypatch) -> None:
    import pytest

    from app.errors import ExternalServiceError
    from app.services.wordpress import publish_wordpress_post, validate_wordpress_site_url

    with pytest.raises(ExternalServiceError, match="HTTPS"):
        validate_wordpress_site_url("http://example.com")
    assert validate_wordpress_site_url("http://127.0.0.1:8080/site/") == "http://127.0.0.1:8080/site"

    captured: dict = {}

    async def fake_request(site_url, username, application_password, resource, **kwargs):
        captured.update(
            {
                "site_url": site_url,
                "username": username,
                "application_password": application_password,
                "resource": resource,
                **kwargs,
            }
        )
        return {"id": 9, "link": "https://example.com/safe-post/"}

    monkeypatch.setattr("app.services.wordpress.wordpress_request", fake_request)
    result = asyncio.run(
        publish_wordpress_post(
            "https://example.com",
            "editor",
            "application-password",
            {
                "title": "Safe post",
                "body": "Approved <script>alert('no')</script>\n\nSecond line",
                "hashtags": ["#approved", "reviewed"],
            },
        )
    )
    assert result.remote_id == "9"
    assert result.remote_url == "https://example.com/safe-post/"
    assert captured["resource"] == "posts"
    assert captured["method"] == "POST"
    assert captured["json_body"] == {
        "title": "Safe post",
        "content": (
            "<p>Approved &lt;script&gt;alert(&#x27;no&#x27;)&lt;/script&gt;</p>\n"
            "<p>Second line</p>\n<p>#approved #reviewed</p>"
        ),
        "status": "publish",
    }


def test_meta_connector_publishes_exact_approved_facebook_revision(client, monkeypatch) -> None:
    from app.connectors.base import ConnectorTestResult
    from app.schemas import GeneratedContent
    from app.services.meta import MetaPublishResult

    catalog = client.get("/api/connectors").json()["catalog"]
    manifest = next(item for item in catalog if item["adapterId"] == "meta")
    assert manifest["name"] == "Meta Pages"
    assert manifest["availability"] == "available"
    assert manifest["capabilities"] == ["publish"]
    assert manifest["requiredScopes"] == ["pages_read_engagement", "pages_manage_posts"]

    page_id = "123456789012345"
    page_access_token = "encrypted-page-access-token"
    created = client.post(
        "/api/connectors",
        json={
            "adapterId": "meta",
            "name": "Company Facebook Page",
            "config": {"page_id": page_id, "api_version": "v25.0"},
            "secrets": {"page_access_token": page_access_token},
            "scopes": ["pages_read_engagement", "pages_manage_posts"],
            "enabled": True,
        },
    )
    assert created.status_code == 200
    account = created.json()["account"]
    assert account["secretStatus"] == {"page_access_token": True}
    assert page_access_token not in created.text

    async def fake_meta_test(_self, config, secrets):
        assert config == {"page_id": page_id, "api_version": "v25.0"}
        assert secrets == {"page_access_token": page_access_token}
        return ConnectorTestResult(
            ok=True,
            message="Connected to Facebook Page Northstar Studio.",
            remote_account_id=page_id,
            details={"pageId": page_id, "page": "Northstar Studio", "apiVersion": "v25.0"},
        )

    monkeypatch.setattr("app.connectors.meta.MetaPagesAdapter.test_connection", fake_meta_test)
    tested = client.post(f"/api/connectors/{account['id']}/test")
    assert tested.status_code == 200
    assert tested.json()["remoteAccountId"] == page_id

    async def fake_generate(*_args, **_kwargs):
        return GeneratedContent(
            title="Approved Facebook update",
            body="This exact reviewed message should reach the connected Page.",
            hashtags=["#local", "growth"],
            rationale="Exercises the official Meta Pages publisher.",
        )

    delivered: list[dict] = []

    async def fake_meta_publish(saved_page_id, api_version, saved_token, post):
        assert saved_page_id == page_id
        assert api_version == "v25.0"
        assert saved_token == page_access_token
        delivered.append(post)
        return MetaPublishResult(remote_id=f"{page_id}_987654321")

    monkeypatch.setattr("app.main.generate_content", fake_generate)
    monkeypatch.setattr("app.services.publishing.publish_facebook_page_post", fake_meta_publish)
    generated = client.post(
        "/api/posts/generate",
        json={
            "topic": "Facebook launch",
            "channel": "facebook",
            "tone": "Clear",
            "objective": "Publish the approved Page update",
            "notifyTelegram": False,
        },
    )
    assert generated.status_code == 200
    post = generated.json()["post"]
    approved = client.post(
        f"/api/posts/{post['id']}/decision",
        json={"decision": "approve", "revision": post["revision"]},
    )
    assert approved.status_code == 200

    published = client.post(
        f"/api/posts/{post['id']}/publish",
        json={"revision": post["revision"]},
    )
    assert published.status_code == 200
    final_post = next(item for item in published.json()["state"]["posts"] if item["id"] == post["id"])
    assert final_post["status"] == "published"
    assert final_post["remoteId"] == f"{page_id}_987654321"
    assert final_post["remoteUrl"] is None
    assert len(delivered) == 1
    assert delivered[0]["revision"] == post["revision"]
    assert delivered[0]["body"] == post["body"]
    assert delivered[0]["hashtags"] == post["hashtags"]

    duplicate = client.post(
        f"/api/posts/{post['id']}/publish",
        json={"revision": post["revision"]},
    )
    assert duplicate.status_code == 400
    assert len(delivered) == 1

    client.put("/api/scheduler", json={"paused": True})
    scheduled_post = client.post(
        "/api/posts/generate",
        json={
            "topic": "Scheduled Facebook update",
            "channel": "facebook",
            "tone": "Clear",
            "objective": "Verify the Meta Pages scheduler dispatch",
            "notifyTelegram": False,
        },
    ).json()["post"]
    client.post(
        f"/api/posts/{scheduled_post['id']}/decision",
        json={"decision": "approve", "revision": scheduled_post["revision"]},
    )
    scheduled = client.post(
        f"/api/posts/{scheduled_post['id']}/schedule",
        json={
            "revision": scheduled_post["revision"],
            "runAt": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
        },
    )
    assert scheduled.status_code == 200
    client.put("/api/scheduler", json={"paused": False})

    deadline = time.monotonic() + 3
    scheduled_state = client.get("/api/state").json()
    while time.monotonic() < deadline:
        scheduled_state = client.get("/api/state").json()
        current = next(item for item in scheduled_state["posts"] if item["id"] == scheduled_post["id"])
        if current["status"] == "published":
            break
        time.sleep(0.05)
    current = next(item for item in scheduled_state["posts"] if item["id"] == scheduled_post["id"])
    job = next(item for item in scheduled_state["jobs"] if item["id"] == scheduled.json()["job"]["id"])
    assert current["status"] == "published"
    assert current["remoteId"] == f"{page_id}_987654321"
    assert job["status"] == "completed"
    assert len(delivered) == 2


def test_meta_payload_and_graph_endpoint_validation(monkeypatch) -> None:
    import httpx

    from app.errors import ExternalServiceError
    from app.services.meta import (
        approved_facebook_message,
        meta_graph_request,
        publish_facebook_page_post,
        validate_meta_api_version,
        validate_meta_graph_base_url,
        validate_meta_page_id,
    )

    with pytest.raises(ExternalServiceError, match="HTTPS"):
        validate_meta_graph_base_url("http://graph.example.com")
    assert validate_meta_graph_base_url("http://127.0.0.1:4100/meta/") == "http://127.0.0.1:4100/meta"
    with pytest.raises(ExternalServiceError, match="version"):
        validate_meta_api_version("latest")
    with pytest.raises(ExternalServiceError, match="Page ID"):
        validate_meta_page_id("northstar-page")

    assert approved_facebook_message(
        {"body": "Approved body", "hashtags": ["#Socium", "Reviewed"]}
    ) == "Approved body\n\n#Socium #Reviewed"

    leaked_token = "page-token-that-must-not-leak"
    request_capture: dict = {}

    class FakeAsyncClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def request(self, method, endpoint, **kwargs):
            request_capture.update({"method": method, "endpoint": endpoint, **kwargs})
            return httpx.Response(
                400,
                json={"error": {"code": 190, "message": f"Invalid token {leaked_token}"}},
            )

    monkeypatch.setattr("app.services.meta.httpx.AsyncClient", FakeAsyncClient)
    with pytest.raises(ExternalServiceError) as error:
        asyncio.run(
            meta_graph_request(
                "123456789012345",
                leaked_token,
                api_version="v25.0",
                params={"fields": "id,name"},
            )
        )
    assert leaked_token not in str(error.value)
    assert "[redacted]" in str(error.value)
    assert leaked_token not in request_capture["endpoint"]
    assert request_capture["headers"]["Authorization"] == f"Bearer {leaked_token}"

    captured: dict = {}

    async def fake_request(page_id, page_access_token, resource="", **kwargs):
        captured.update(
            {
                "page_id": page_id,
                "page_access_token": page_access_token,
                "resource": resource,
                **kwargs,
            }
        )
        return {"id": "123456789012345_987654321"}

    monkeypatch.setattr("app.services.meta.meta_graph_request", fake_request)
    result = asyncio.run(
        publish_facebook_page_post(
            "123456789012345",
            "v25.0",
            "secret-page-token",
            {"body": "Approved body", "hashtags": ["#Socium", "Reviewed"]},
        )
    )
    assert result.remote_id == "123456789012345_987654321"
    assert captured == {
        "page_id": "123456789012345",
        "page_access_token": "secret-page-token",
        "resource": "feed",
        "api_version": "v25.0",
        "method": "POST",
        "data": {"message": "Approved body\n\n#Socium #Reviewed"},
        "timeout": 45,
    }


def test_instagram_connector_publishes_exact_approved_image_revision(client, monkeypatch) -> None:
    from app.connectors.base import ConnectorTestResult
    from app.schemas import GeneratedContent
    from app.services.instagram import InstagramPublishResult

    catalog = client.get("/api/connectors").json()["catalog"]
    manifest = next(item for item in catalog if item["adapterId"] == "instagram")
    assert manifest["name"] == "Instagram Professional"
    assert manifest["availability"] == "available"
    assert manifest["capabilities"] == ["publish"]
    assert manifest["requiredScopes"] == [
        "instagram_business_basic",
        "instagram_business_content_publish",
    ]

    user_id = "17841400000000000"
    access_token = "encrypted-instagram-access-token"
    image_url = "https://cdn.example.com/campaign.jpg?signature=approved"
    created = client.post(
        "/api/connectors",
        json={
            "adapterId": "instagram",
            "name": "Company Instagram",
            "config": {"user_id": user_id, "api_version": "v25.0"},
            "secrets": {"access_token": access_token},
            "scopes": ["instagram_business_basic", "instagram_business_content_publish"],
            "enabled": True,
        },
    )
    assert created.status_code == 200
    account = created.json()["account"]
    assert account["secretStatus"] == {"access_token": True}
    assert access_token not in created.text

    async def fake_instagram_test(_self, config, secrets):
        assert config == {"user_id": user_id, "api_version": "v25.0"}
        assert secrets == {"access_token": access_token}
        return ConnectorTestResult(
            ok=True,
            message="Connected to Instagram @northstarstudio.",
            remote_account_id=user_id,
            details={
                "userId": user_id,
                "username": "northstarstudio",
                "accountType": "BUSINESS",
                "apiVersion": "v25.0",
            },
        )

    monkeypatch.setattr(
        "app.connectors.instagram.InstagramAdapter.test_connection",
        fake_instagram_test,
    )
    tested = client.post(f"/api/connectors/{account['id']}/test")
    assert tested.status_code == 200
    assert tested.json()["remoteAccountId"] == user_id

    async def fake_generate(*_args, **_kwargs):
        return GeneratedContent(
            title="Approved Instagram image",
            body="This exact reviewed caption should reach the professional account.",
            hashtags=["#local", "growth"],
            rationale="Exercises the official Instagram container publisher.",
        )

    delivered: list[dict] = []

    async def fake_instagram_publish(saved_user_id, api_version, saved_token, post):
        assert saved_user_id == user_id
        assert api_version == "v25.0"
        assert saved_token == access_token
        delivered.append(post)
        return InstagramPublishResult(remote_id="18000000000000001")

    monkeypatch.setattr("app.main.generate_content", fake_generate)
    monkeypatch.setattr("app.services.publishing.publish_instagram_image", fake_instagram_publish)
    generated = client.post(
        "/api/posts/generate",
        json={
            "topic": "Instagram launch",
            "channel": "instagram",
            "tone": "Clear",
            "objective": "Publish the approved image and caption",
            "mediaUrl": image_url,
            "notifyTelegram": False,
        },
    )
    assert generated.status_code == 200
    post = generated.json()["post"]
    assert post["mediaUrl"] == image_url
    approved = client.post(
        f"/api/posts/{post['id']}/decision",
        json={"decision": "approve", "revision": post["revision"]},
    )
    assert approved.status_code == 200

    published = client.post(
        f"/api/posts/{post['id']}/publish",
        json={"revision": post["revision"]},
    )
    assert published.status_code == 200
    final_post = next(item for item in published.json()["state"]["posts"] if item["id"] == post["id"])
    assert final_post["status"] == "published"
    assert final_post["remoteId"] == "18000000000000001"
    assert final_post["mediaUrl"] == image_url
    assert len(delivered) == 1
    assert delivered[0]["revision"] == post["revision"]
    assert delivered[0]["body"] == post["body"]
    assert delivered[0]["hashtags"] == post["hashtags"]
    assert delivered[0]["mediaUrl"] == image_url

    duplicate = client.post(
        f"/api/posts/{post['id']}/publish",
        json={"revision": post["revision"]},
    )
    assert duplicate.status_code == 400
    assert len(delivered) == 1

    client.put("/api/scheduler", json={"paused": True})
    scheduled_url = "https://cdn.example.com/scheduled.jpg"
    scheduled_post = client.post(
        "/api/posts/generate",
        json={
            "topic": "Scheduled Instagram image",
            "channel": "instagram",
            "tone": "Clear",
            "objective": "Verify the Instagram scheduler dispatch",
            "mediaUrl": scheduled_url,
            "notifyTelegram": False,
        },
    ).json()["post"]
    client.post(
        f"/api/posts/{scheduled_post['id']}/decision",
        json={"decision": "approve", "revision": scheduled_post["revision"]},
    )
    scheduled = client.post(
        f"/api/posts/{scheduled_post['id']}/schedule",
        json={
            "revision": scheduled_post["revision"],
            "runAt": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
        },
    )
    assert scheduled.status_code == 200
    client.put("/api/scheduler", json={"paused": False})

    deadline = time.monotonic() + 3
    scheduled_state = client.get("/api/state").json()
    while time.monotonic() < deadline:
        scheduled_state = client.get("/api/state").json()
        current = next(item for item in scheduled_state["posts"] if item["id"] == scheduled_post["id"])
        if current["status"] == "published":
            break
        time.sleep(0.05)
    current = next(item for item in scheduled_state["posts"] if item["id"] == scheduled_post["id"])
    job = next(item for item in scheduled_state["jobs"] if item["id"] == scheduled.json()["job"]["id"])
    assert current["status"] == "published"
    assert current["remoteId"] == "18000000000000001"
    assert current["mediaUrl"] == scheduled_url
    assert job["status"] == "completed"
    assert len(delivered) == 2


def test_instagram_media_validation_and_container_publish_flow(monkeypatch) -> None:
    import httpx

    from app.errors import ExternalServiceError
    from app.services.instagram import (
        approved_instagram_caption,
        instagram_graph_request,
        publish_instagram_image,
        validate_instagram_graph_base_url,
        validate_instagram_media_url,
        validate_instagram_user_id,
    )

    with pytest.raises(ExternalServiceError, match="HTTPS"):
        validate_instagram_media_url("http://cdn.example.com/image.jpg")
    with pytest.raises(ExternalServiceError, match="localhost"):
        validate_instagram_media_url("https://localhost/image.jpg")
    with pytest.raises(ExternalServiceError, match="public host"):
        validate_instagram_media_url("https://192.168.1.20/image.jpg")
    assert validate_instagram_media_url(
        "https://cdn.example.com/image.jpg?signature=one-time"
    ) == "https://cdn.example.com/image.jpg?signature=one-time"
    with pytest.raises(ExternalServiceError, match="HTTPS"):
        validate_instagram_graph_base_url("http://graph.example.com")
    assert validate_instagram_graph_base_url(
        "http://127.0.0.1:4100/instagram/"
    ) == "http://127.0.0.1:4100/instagram"
    with pytest.raises(ExternalServiceError, match="Account ID"):
        validate_instagram_user_id("northstar")

    assert approved_instagram_caption(
        {"body": "Approved caption", "hashtags": ["#Socium", "Reviewed"]}
    ) == "Approved caption\n\n#Socium #Reviewed"
    with pytest.raises(ExternalServiceError, match="2,200"):
        approved_instagram_caption({"body": "x" * 2_201, "hashtags": []})

    from app.schemas import EditPostRequest, GeneratePostRequest

    with pytest.raises(ValueError, match="public HTTPS"):
        GeneratePostRequest(
            topic="Unsafe image",
            channel="instagram",
            mediaUrl="javascript:alert(1)",
        )
    with pytest.raises(ValueError, match="localhost"):
        EditPostRequest(
            title="Unsafe image",
            body="Reviewed body",
            mediaUrl="https://localhost/image.jpg",
        )

    leaked_token = "instagram-token-that-must-not-leak"
    request_capture: dict = {}

    class FakeAsyncClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def request(self, method, endpoint, **kwargs):
            request_capture.update({"method": method, "endpoint": endpoint, **kwargs})
            return httpx.Response(
                400,
                json={"error": {"code": 190, "message": f"Invalid token {leaked_token}"}},
            )

    monkeypatch.setattr("app.services.instagram.httpx.AsyncClient", FakeAsyncClient)
    with pytest.raises(ExternalServiceError) as error:
        asyncio.run(
            instagram_graph_request(
                "17841400000000000",
                leaked_token,
                api_version="v25.0",
                params={"fields": "id,username,account_type"},
            )
        )
    assert leaked_token not in str(error.value)
    assert "[redacted]" in str(error.value)
    assert leaked_token not in request_capture["endpoint"]
    assert request_capture["headers"]["Authorization"] == f"Bearer {leaked_token}"

    calls: list[dict] = []

    async def fake_request(subject_id, access_token, resource="", **kwargs):
        calls.append(
            {
                "subject_id": subject_id,
                "access_token": access_token,
                "resource": resource,
                **kwargs,
            }
        )
        if resource == "media":
            return {"id": "18000000000000010"}
        if subject_id == "18000000000000010":
            return {"status_code": "FINISHED", "status": "Finished"}
        return {"id": "18000000000000011"}

    monkeypatch.setattr("app.services.instagram.instagram_graph_request", fake_request)
    result = asyncio.run(
        publish_instagram_image(
            "17841400000000000",
            "v25.0",
            "secret-instagram-token",
            {
                "body": "Approved caption",
                "hashtags": ["#Socium", "Reviewed"],
                "mediaUrl": "https://cdn.example.com/image.jpg?signature=one-time",
            },
            status_delay=0,
        )
    )
    assert result.remote_id == "18000000000000011"
    assert calls == [
        {
            "subject_id": "17841400000000000",
            "access_token": "secret-instagram-token",
            "resource": "media",
            "api_version": "v25.0",
            "method": "POST",
            "data": {
                "image_url": "https://cdn.example.com/image.jpg?signature=one-time",
                "caption": "Approved caption\n\n#Socium #Reviewed",
            },
            "timeout": 45,
        },
        {
            "subject_id": "18000000000000010",
            "access_token": "secret-instagram-token",
            "resource": "",
            "api_version": "v25.0",
            "params": {"fields": "status_code,status"},
            "timeout": 15,
        },
        {
            "subject_id": "17841400000000000",
            "access_token": "secret-instagram-token",
            "resource": "media_publish",
            "api_version": "v25.0",
            "method": "POST",
            "data": {"creation_id": "18000000000000010"},
            "timeout": 45,
        },
    ]


def test_linkedin_connector_publishes_exact_approved_member_revision(client, monkeypatch) -> None:
    from app.connectors.base import ConnectorTestResult
    from app.schemas import GeneratedContent
    from app.services.linkedin import LinkedInPublishResult

    catalog = client.get("/api/connectors").json()["catalog"]
    manifest = next(item for item in catalog if item["adapterId"] == "linkedin")
    assert manifest["name"] == "LinkedIn Member"
    assert manifest["availability"] == "available"
    assert manifest["capabilities"] == ["publish"]
    assert manifest["requiredScopes"] == ["openid", "profile", "w_member_social"]

    person_id = "782bbtaQ"
    access_token = "encrypted-linkedin-oauth-token"
    created = client.post(
        "/api/connectors",
        json={
            "adapterId": "linkedin",
            "name": "Founder profile",
            "config": {"person_id": person_id, "api_version": "202607"},
            "secrets": {"access_token": access_token},
            "scopes": ["openid", "profile", "w_member_social"],
            "enabled": True,
        },
    )
    assert created.status_code == 200
    account = created.json()["account"]
    assert account["secretStatus"] == {"access_token": True}
    assert access_token not in created.text

    async def fake_linkedin_test(_self, config, secrets):
        assert config == {"person_id": person_id, "api_version": "202607"}
        assert secrets == {"access_token": access_token}
        return ConnectorTestResult(
            ok=True,
            message="Connected to LinkedIn as Waleed Khan.",
            remote_account_id=person_id,
            details={"personId": person_id, "name": "Waleed Khan", "apiVersion": "202607"},
        )

    monkeypatch.setattr(
        "app.connectors.linkedin.LinkedInMemberAdapter.test_connection",
        fake_linkedin_test,
    )
    tested = client.post(f"/api/connectors/{account['id']}/test")
    assert tested.status_code == 200
    assert tested.json()["remoteAccountId"] == person_id

    async def fake_generate(*_args, **_kwargs):
        return GeneratedContent(
            title="Approved LinkedIn update",
            body="This exact reviewed update should reach the connected member profile.",
            hashtags=["#Socium", "HumanReviewed"],
            rationale="Exercises the official LinkedIn Posts publisher.",
        )

    delivered: list[dict] = []

    async def fake_linkedin_publish(saved_person_id, api_version, saved_token, post):
        assert saved_person_id == person_id
        assert api_version == "202607"
        assert saved_token == access_token
        delivered.append(post)
        return LinkedInPublishResult(remote_id="urn:li:share:7190000000000000001")

    monkeypatch.setattr("app.main.generate_content", fake_generate)
    monkeypatch.setattr(
        "app.services.publishing.publish_linkedin_member_post",
        fake_linkedin_publish,
    )
    generated = client.post(
        "/api/posts/generate",
        json={
            "topic": "LinkedIn launch",
            "channel": "linkedin",
            "tone": "Clear",
            "objective": "Publish the exact approved member update",
            "notifyTelegram": False,
        },
    )
    assert generated.status_code == 200
    post = generated.json()["post"]
    approved = client.post(
        f"/api/posts/{post['id']}/decision",
        json={"decision": "approve", "revision": post["revision"]},
    )
    assert approved.status_code == 200

    published = client.post(
        f"/api/posts/{post['id']}/publish",
        json={"revision": post["revision"]},
    )
    assert published.status_code == 200
    final_post = next(item for item in published.json()["state"]["posts"] if item["id"] == post["id"])
    assert final_post["status"] == "published"
    assert final_post["remoteId"] == "urn:li:share:7190000000000000001"
    assert len(delivered) == 1
    assert delivered[0]["revision"] == post["revision"]
    assert delivered[0]["body"] == post["body"]
    assert delivered[0]["hashtags"] == post["hashtags"]

    duplicate = client.post(
        f"/api/posts/{post['id']}/publish",
        json={"revision": post["revision"]},
    )
    assert duplicate.status_code == 400
    assert len(delivered) == 1

    client.put("/api/scheduler", json={"paused": True})
    scheduled_post = client.post(
        "/api/posts/generate",
        json={
            "topic": "Scheduled LinkedIn update",
            "channel": "linkedin",
            "tone": "Clear",
            "objective": "Verify the LinkedIn scheduler dispatch",
            "notifyTelegram": False,
        },
    ).json()["post"]
    client.post(
        f"/api/posts/{scheduled_post['id']}/decision",
        json={"decision": "approve", "revision": scheduled_post["revision"]},
    )
    scheduled = client.post(
        f"/api/posts/{scheduled_post['id']}/schedule",
        json={
            "revision": scheduled_post["revision"],
            "runAt": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
        },
    )
    assert scheduled.status_code == 200
    client.put("/api/scheduler", json={"paused": False})

    deadline = time.monotonic() + 3
    scheduled_state = client.get("/api/state").json()
    while time.monotonic() < deadline:
        scheduled_state = client.get("/api/state").json()
        current = next(item for item in scheduled_state["posts"] if item["id"] == scheduled_post["id"])
        if current["status"] == "published":
            break
        time.sleep(0.05)
    current = next(item for item in scheduled_state["posts"] if item["id"] == scheduled_post["id"])
    job = next(item for item in scheduled_state["jobs"] if item["id"] == scheduled.json()["job"]["id"])
    assert current["status"] == "published"
    assert current["remoteId"] == "urn:li:share:7190000000000000001"
    assert job["status"] == "completed"
    assert len(delivered) == 2


def test_linkedin_payload_versioning_and_token_redaction(monkeypatch) -> None:
    import httpx

    from app.errors import ExternalServiceError
    from app.services.linkedin import (
        LinkedInApiResponse,
        approved_linkedin_commentary,
        linkedin_api_request,
        publish_linkedin_member_post,
        validate_linkedin_api_base_url,
        validate_linkedin_person_id,
        validate_linkedin_version,
    )

    with pytest.raises(ExternalServiceError, match="HTTPS"):
        validate_linkedin_api_base_url("http://api.example.com")
    assert validate_linkedin_api_base_url(
        "http://127.0.0.1:4100/linkedin/"
    ) == "http://127.0.0.1:4100/linkedin"
    with pytest.raises(ExternalServiceError, match="YYYYMM"):
        validate_linkedin_version("latest")
    assert validate_linkedin_version("202607") == "202607"
    with pytest.raises(ExternalServiceError, match="unsupported"):
        validate_linkedin_person_id("member:id")

    assert approved_linkedin_commentary(
        {"body": "Approved update", "hashtags": ["#Socium", "Reviewed"]}
    ) == "Approved update\n\n#Socium #Reviewed"
    with pytest.raises(ExternalServiceError, match="3,000"):
        approved_linkedin_commentary({"body": "x" * 3_001, "hashtags": []})

    leaked_token = "linkedin-token-that-must-not-leak"
    request_capture: dict = {}

    class FakeAsyncClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def request(self, method, endpoint, **kwargs):
            request_capture.update({"method": method, "endpoint": endpoint, **kwargs})
            return httpx.Response(
                401,
                json={"status": 401, "message": f"Invalid token {leaked_token}"},
            )

    monkeypatch.setattr("app.services.linkedin.httpx.AsyncClient", FakeAsyncClient)
    with pytest.raises(ExternalServiceError) as error:
        asyncio.run(linkedin_api_request("v2/userinfo", leaked_token))
    assert leaked_token not in str(error.value)
    assert "[redacted]" in str(error.value)
    assert leaked_token not in request_capture["endpoint"]
    assert request_capture["headers"]["Authorization"] == f"Bearer {leaked_token}"

    calls: list[dict] = []

    async def fake_request(resource, access_token, **kwargs):
        calls.append({"resource": resource, "access_token": access_token, **kwargs})
        return LinkedInApiResponse(
            payload={},
            headers={"x-restli-id": "urn:li:share:7190000000000000002"},
        )

    monkeypatch.setattr("app.services.linkedin.linkedin_api_request", fake_request)
    result = asyncio.run(
        publish_linkedin_member_post(
            "782bbtaQ",
            "202607",
            "secret-linkedin-token",
            {"body": "Approved update", "hashtags": ["#Socium", "Reviewed"]},
        )
    )
    assert result.remote_id == "urn:li:share:7190000000000000002"
    assert calls == [
        {
            "resource": "rest/posts",
            "access_token": "secret-linkedin-token",
            "method": "POST",
            "api_version": "202607",
            "json_body": {
                "author": "urn:li:person:782bbtaQ",
                "commentary": "Approved update\n\n#Socium #Reviewed",
                "visibility": "PUBLIC",
                "distribution": {
                    "feedDistribution": "MAIN_FEED",
                    "targetEntities": [],
                    "thirdPartyDistributionChannels": [],
                },
                "lifecycleState": "PUBLISHED",
                "isReshareDisabledByAuthor": False,
            },
            "timeout": 45,
        }
    ]


def test_linkedin_company_connector_publishes_exact_approved_page_revision(client, monkeypatch) -> None:
    from app.connectors.base import ConnectorTestResult
    from app.schemas import GeneratedContent
    from app.services.linkedin import LinkedInPublishResult

    catalog = client.get("/api/connectors").json()["catalog"]
    manifest = next(item for item in catalog if item["adapterId"] == "linkedin-organization")
    assert manifest["name"] == "LinkedIn Company Page"
    assert manifest["availability"] == "access-gated"
    assert manifest["capabilities"] == ["publish"]
    assert manifest["requiredScopes"] == [
        "openid",
        "profile",
        "w_organization_social",
        "rw_organization_admin",
    ]

    person_id = "782bbtaQ"
    organization_id = "5515715"
    access_token = "encrypted-linkedin-company-token"
    created = client.post(
        "/api/connectors",
        json={
            "adapterId": "linkedin-organization",
            "name": "Socium Company Page",
            "config": {
                "person_id": person_id,
                "organization_id": organization_id,
                "api_version": "202607",
            },
            "secrets": {"access_token": access_token},
            "scopes": [
                "openid",
                "profile",
                "w_organization_social",
                "rw_organization_admin",
            ],
            "enabled": True,
        },
    )
    assert created.status_code == 200
    account = created.json()["account"]
    assert account["secretStatus"] == {"access_token": True}
    assert access_token not in created.text

    async def fake_company_test(_self, config, secrets):
        assert config == {
            "person_id": person_id,
            "organization_id": organization_id,
            "api_version": "202607",
        }
        assert secrets == {"access_token": access_token}
        return ConnectorTestResult(
            ok=True,
            message="Waleed Khan can publish to LinkedIn Page 5515715.",
            remote_account_id=organization_id,
            details={
                "personId": person_id,
                "name": "Waleed Khan",
                "organizationId": organization_id,
                "organizationUrn": f"urn:li:organization:{organization_id}",
                "authorization": "ORGANIC_SHARE_CREATE",
                "apiVersion": "202607",
            },
        )

    monkeypatch.setattr(
        "app.connectors.linkedin.LinkedInOrganizationAdapter.test_connection",
        fake_company_test,
    )
    tested = client.post(f"/api/connectors/{account['id']}/test")
    assert tested.status_code == 200
    assert tested.json()["remoteAccountId"] == organization_id

    async def fake_generate(*_args, **_kwargs):
        return GeneratedContent(
            title="Approved LinkedIn Company update",
            body="This exact reviewed update should reach the connected Company Page.",
            hashtags=["#Socium", "CompanyReviewed"],
            rationale="Exercises the official LinkedIn organization Posts publisher.",
        )

    delivered: list[dict] = []

    async def fake_company_publish(saved_organization_id, api_version, saved_token, post):
        assert saved_organization_id == organization_id
        assert api_version == "202607"
        assert saved_token == access_token
        delivered.append(post)
        return LinkedInPublishResult(remote_id="urn:li:share:7190000000000000010")

    monkeypatch.setattr("app.main.generate_content", fake_generate)
    monkeypatch.setattr(
        "app.services.publishing.publish_linkedin_organization_post",
        fake_company_publish,
    )
    generated = client.post(
        "/api/posts/generate",
        json={
            "topic": "LinkedIn Company launch",
            "channel": "linkedin-company",
            "tone": "Clear",
            "objective": "Publish the exact approved Page update",
            "notifyTelegram": False,
        },
    )
    assert generated.status_code == 200
    post = generated.json()["post"]
    approved = client.post(
        f"/api/posts/{post['id']}/decision",
        json={"decision": "approve", "revision": post["revision"]},
    )
    assert approved.status_code == 200

    published = client.post(
        f"/api/posts/{post['id']}/publish",
        json={"revision": post["revision"]},
    )
    assert published.status_code == 200
    final_post = next(item for item in published.json()["state"]["posts"] if item["id"] == post["id"])
    assert final_post["status"] == "published"
    assert final_post["remoteId"] == "urn:li:share:7190000000000000010"
    assert len(delivered) == 1
    assert delivered[0]["revision"] == post["revision"]
    assert delivered[0]["body"] == post["body"]
    assert delivered[0]["hashtags"] == post["hashtags"]

    duplicate = client.post(
        f"/api/posts/{post['id']}/publish",
        json={"revision": post["revision"]},
    )
    assert duplicate.status_code == 400
    assert len(delivered) == 1

    client.put("/api/scheduler", json={"paused": True})
    scheduled_post = client.post(
        "/api/posts/generate",
        json={
            "topic": "Scheduled LinkedIn Company update",
            "channel": "linkedin-company",
            "tone": "Clear",
            "objective": "Verify the Company Page scheduler dispatch",
            "notifyTelegram": False,
        },
    ).json()["post"]
    client.post(
        f"/api/posts/{scheduled_post['id']}/decision",
        json={"decision": "approve", "revision": scheduled_post["revision"]},
    )
    scheduled = client.post(
        f"/api/posts/{scheduled_post['id']}/schedule",
        json={
            "revision": scheduled_post["revision"],
            "runAt": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
        },
    )
    assert scheduled.status_code == 200
    client.put("/api/scheduler", json={"paused": False})

    deadline = time.monotonic() + 3
    scheduled_state = client.get("/api/state").json()
    while time.monotonic() < deadline:
        scheduled_state = client.get("/api/state").json()
        current = next(item for item in scheduled_state["posts"] if item["id"] == scheduled_post["id"])
        if current["status"] == "published":
            break
        time.sleep(0.05)
    current = next(item for item in scheduled_state["posts"] if item["id"] == scheduled_post["id"])
    job = next(item for item in scheduled_state["jobs"] if item["id"] == scheduled.json()["job"]["id"])
    assert current["status"] == "published"
    assert current["remoteId"] == "urn:li:share:7190000000000000010"
    assert job["status"] == "completed"
    assert len(delivered) == 2


def test_linkedin_company_authorization_and_payload(monkeypatch) -> None:
    from app.errors import ExternalServiceError
    from app.services.linkedin import (
        LinkedInApiResponse,
        publish_linkedin_organization_post,
        test_linkedin_organization_connection,
        validate_linkedin_organization_id,
    )

    assert validate_linkedin_organization_id("5515715") == "5515715"
    with pytest.raises(ExternalServiceError, match="digits"):
        validate_linkedin_organization_id("urn:li:organization:5515715")

    async def fake_member_test(person_id, access_token):
        assert person_id == "782bbtaQ"
        assert access_token == "secret-company-token"
        return {"personId": person_id, "name": "Waleed Khan"}

    authorization_calls: list[dict] = []

    async def fake_authorization_request(resource, access_token, **kwargs):
        authorization_calls.append({"resource": resource, "access_token": access_token, **kwargs})
        return LinkedInApiResponse(
            payload={
                "impersonator": "urn:li:person:782bbtaQ",
                "organization": "urn:li:organization:5515715",
                "status": {"com.linkedin.organization.Approved": {}},
            },
            headers={},
        )

    monkeypatch.setattr("app.services.linkedin.test_linkedin_connection", fake_member_test)
    monkeypatch.setattr("app.services.linkedin.linkedin_api_request", fake_authorization_request)
    details = asyncio.run(
        test_linkedin_organization_connection(
            "782bbtaQ",
            "5515715",
            "202607",
            "secret-company-token",
        )
    )
    assert details["organizationUrn"] == "urn:li:organization:5515715"
    assert details["authorization"] == "ORGANIC_SHARE_CREATE"
    assert authorization_calls == [
        {
            "resource": (
                "rest/organizationAuthorizations/"
                "(impersonator:urn%3Ali%3Aperson%3A782bbtaQ,"
                "organization:urn%3Ali%3Aorganization%3A5515715,"
                "action:(organizationContentAuthorizationAction:"
                "(actionType:ORGANIC_SHARE_CREATE)))"
            ),
            "access_token": "secret-company-token",
            "api_version": "202607",
            "timeout": 20,
        }
    ]

    async def fake_denied_request(*_args, **_kwargs):
        return LinkedInApiResponse(
            payload={
                "impersonator": "urn:li:person:782bbtaQ",
                "organization": "urn:li:organization:5515715",
                "status": {
                    "com.linkedin.organization.Denied": {
                        "reasons": ["MEMBER_HAS_INSUFFICIENT_PERMISSIONS_IN_ACCESS_CONTROL"]
                    }
                },
            },
            headers={},
        )

    monkeypatch.setattr("app.services.linkedin.linkedin_api_request", fake_denied_request)
    with pytest.raises(ExternalServiceError, match="not authorized"):
        asyncio.run(
            test_linkedin_organization_connection(
                "782bbtaQ",
                "5515715",
                "202607",
                "secret-company-token",
            )
        )

    publish_calls: list[dict] = []

    async def fake_publish_request(resource, access_token, **kwargs):
        publish_calls.append({"resource": resource, "access_token": access_token, **kwargs})
        return LinkedInApiResponse(
            payload={},
            headers={"x-restli-id": "urn:li:share:7190000000000000011"},
        )

    monkeypatch.setattr("app.services.linkedin.linkedin_api_request", fake_publish_request)
    result = asyncio.run(
        publish_linkedin_organization_post(
            "5515715",
            "202607",
            "secret-company-token",
            {"body": "Approved Page update", "hashtags": ["#Socium", "Reviewed"]},
        )
    )
    assert result.remote_id == "urn:li:share:7190000000000000011"
    assert publish_calls[0]["resource"] == "rest/posts"
    assert publish_calls[0]["api_version"] == "202607"
    assert publish_calls[0]["json_body"] == {
        "author": "urn:li:organization:5515715",
        "commentary": "Approved Page update\n\n#Socium #Reviewed",
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }


def test_local_media_library_uploads_deduplicates_transforms_and_deletes(client) -> None:
    from io import BytesIO

    from PIL import Image

    source = BytesIO()
    Image.new("RGB", (120, 80), color=(18, 130, 82)).save(source, format="PNG")
    source_bytes = source.getvalue()

    uploaded = client.post(
        "/api/media",
        files={"file": ("../campaign.png", source_bytes, "application/octet-stream")},
    )
    assert uploaded.status_code == 200
    uploaded_payload = uploaded.json()
    assert uploaded_payload["deduplicated"] is False
    asset = uploaded_payload["asset"]
    assert asset["originalName"] == "campaign.png"
    assert asset["mimeType"] == "image/png"
    assert asset["width"] == 120
    assert asset["height"] == 80
    assert asset["instagramReady"] is False
    assert len(asset["sha256"]) == 64

    content = client.get(asset["contentUrl"])
    assert content.status_code == 200
    assert content.content == source_bytes
    assert content.headers["content-type"] == "image/png"
    assert content.headers["x-content-type-options"] == "nosniff"

    preview = client.get(asset["previewUrl"])
    assert preview.status_code == 200
    assert preview.headers["content-type"] == "image/webp"
    with Image.open(BytesIO(preview.content)) as preview_image:
        assert preview_image.size == (120, 80)

    duplicate = client.post(
        "/api/media",
        files={"file": ("renamed.png", source_bytes, "image/png")},
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["deduplicated"] is True
    assert duplicate.json()["asset"]["id"] == asset["id"]

    invalid = client.post(
        "/api/media",
        files={"file": ("fake.png", b"not-an-image", "image/png")},
    )
    assert invalid.status_code == 400
    assert "valid JPEG, PNG, or WebP" in invalid.json()["error"]

    oversized = client.post(
        "/api/media",
        files={"file": ("oversized.png", b"x" * (10 * 1024 * 1024 + 1), "image/png")},
    )
    assert oversized.status_code == 413
    assert oversized.json()["error"] == "Images must be 10 MB or smaller."

    metadata = client.patch(
        f"/api/media/{asset['id']}",
        json={
            "altText": "A green campaign card for Northstar Studio",
            "publicSourceUrl": "https://cdn.example.test/campaign.png",
        },
    )
    assert metadata.status_code == 200
    assert metadata.json()["asset"]["instagramReady"] is True
    assert metadata.json()["asset"]["altText"] == "A green campaign card for Northstar Studio"

    transformed = client.post(
        f"/api/media/{asset['id']}/transform",
        json={"preset": "portrait"},
    )
    assert transformed.status_code == 200
    transformed_asset = transformed.json()["asset"]
    assert transformed_asset["source"] == "transform:portrait"
    assert transformed_asset["sourceAssetId"] == asset["id"]
    assert transformed_asset["width"] == 1080
    assert transformed_asset["height"] == 1350
    transformed_content = client.get(transformed_asset["contentUrl"])
    with Image.open(BytesIO(transformed_content.content)) as transformed_image:
        assert transformed_image.size == (1080, 1350)
        assert transformed_image.format == "WEBP"

    library = client.get("/api/media")
    assert library.status_code == 200
    assert library.headers["cache-control"] == "no-store"
    assert library.json()["storagePolicy"] == "local-only"
    assert library.json()["total"] == 2

    removed_transform = client.delete(f"/api/media/{transformed_asset['id']}")
    assert removed_transform.status_code == 200
    assert client.get(transformed_asset["contentUrl"]).status_code == 404
    removed_source = client.delete(f"/api/media/{asset['id']}")
    assert removed_source.status_code == 200
    assert client.get(asset["previewUrl"]).status_code == 404

    audit = client.get("/api/state").json()["audit"]
    assert any(item["action"] == "media.created" and item["entityId"] == asset["id"] for item in audit)
    assert any(
        item["action"] == "media.transformed" and item["entityId"] == transformed_asset["id"]
        for item in audit
    )
    assert any(item["action"] == "media.deleted" and item["entityId"] == asset["id"] for item in audit)


def test_image_provider_settings_are_separate_and_encrypted(client) -> None:
    saved = client.put(
        "/api/settings/image-provider",
        json={
            "kind": "openai-images",
            "baseUrl": "https://images.example/v1",
            "model": "image-model",
            "apiKey": "image-key-must-stay-encrypted",
        },
    )
    assert saved.status_code == 200
    public = saved.json()["state"]["imageProvider"]
    assert public == {
        "kind": "openai-images",
        "baseUrl": "https://images.example/v1",
        "model": "image-model",
        "hasApiKey": True,
        "hasWorkflow": False,
        "configured": True,
        "updatedAt": public["updatedAt"],
    }

    from app.config import get_settings

    with sqlite3.connect(Path(get_settings().database_path)) as connection:
        encrypted = connection.execute(
            "SELECT api_key FROM image_provider_settings WHERE id = 1"
        ).fetchone()[0]
    assert "image-key-must-stay-encrypted" not in encrypted
    assert "image-key-must-stay-encrypted" not in json.dumps(saved.json())


def test_image_generation_adapters_send_exact_provider_contracts(monkeypatch) -> None:
    from io import BytesIO

    from PIL import Image

    from app.schemas import ImageGenerateRequest
    from app.services import image_generation

    output = BytesIO()
    Image.new("RGB", (2, 2), color=(92, 56, 210)).save(output, format="PNG")
    encoded = __import__("base64").b64encode(output.getvalue()).decode("ascii")
    calls: list[dict[str, object]] = []

    async def fake_request(url: str, **kwargs):
        calls.append({"url": url, **kwargs})
        if url.endswith("/images/generations"):
            return {"data": [{"b64_json": encoded}]}
        return {"images": [encoded], "parameters": {}, "info": "{}"}

    monkeypatch.setattr(image_generation, "_request_json", fake_request)
    openai_result = asyncio.run(
        image_generation.generate_image(
            {
                "kind": "openai-images",
                "base_url": "https://images.example/v1",
                "model": "gpt-image-2",
                "api_key": "hosted-secret",
            },
            ImageGenerateRequest(
                prompt="A precise editorial campaign image",
                preset="portrait",
                quality="high",
            ),
        )
    )
    assert openai_result.data == output.getvalue()
    assert calls[0]["url"] == "https://images.example/v1/images/generations"
    assert calls[0]["headers"] == {
        "Content-Type": "application/json",
        "Authorization": "Bearer hosted-secret",
    }
    assert calls[0]["json_body"] == {
        "model": "gpt-image-2",
        "prompt": "A precise editorial campaign image",
        "n": 1,
        "size": "1024x1536",
        "quality": "high",
        "output_format": "png",
    }

    calls.clear()
    local_result = asyncio.run(
        image_generation.generate_image(
            {
                "kind": "automatic1111",
                "base_url": "http://127.0.0.1:7860",
                "model": "campaign-checkpoint.safetensors",
                "api_key": "operator:secret",
            },
            ImageGenerateRequest(
                prompt="A local campaign visual",
                negativePrompt="watermark",
                preset="landscape",
                steps=32,
                guidanceScale=6.5,
                seed=42,
            ),
        )
    )
    assert local_result.data == output.getvalue()
    assert calls[0]["url"] == "http://127.0.0.1:7860/sdapi/v1/txt2img"
    assert calls[0]["headers"] == {
        "Content-Type": "application/json",
        "Authorization": "Basic b3BlcmF0b3I6c2VjcmV0",
    }
    assert calls[0]["json_body"] == {
        "prompt": "A local campaign visual",
        "negative_prompt": "watermark",
        "width": 1152,
        "height": 896,
        "steps": 32,
        "cfg_scale": 6.5,
        "seed": 42,
        "batch_size": 1,
        "n_iter": 1,
        "override_settings": {"sd_model_checkpoint": "campaign-checkpoint.safetensors"},
        "override_settings_restore_afterwards": True,
    }


def test_generated_image_is_validated_stored_and_audited(client, monkeypatch) -> None:
    from io import BytesIO

    from PIL import Image

    from app.services.image_generation import GeneratedImage

    output = BytesIO()
    Image.new("RGB", (64, 48), color=(34, 211, 238)).save(output, format="PNG")

    async def fake_generate(_settings, request):
        return GeneratedImage(
            data=output.getvalue(),
            provider_kind="openai-images",
            model="image-model",
            parameters={"preset": request.preset, "size": "1536x1024", "quality": request.quality},
        )

    monkeypatch.setattr("app.main.generate_image", fake_generate)
    created = client.post(
        "/api/media/generate",
        json={
            "prompt": "A cyan product launch scene on a black background",
            "preset": "landscape",
            "quality": "medium",
        },
    )
    assert created.status_code == 200
    asset = created.json()["asset"]
    assert asset["source"] == "ai-generated"
    assert asset["generationPrompt"] == "A cyan product launch scene on a black background"
    assert asset["generationProvider"] == "openai-images"
    assert asset["generationModel"] == "image-model"
    assert asset["generationParameters"]["size"] == "1536x1024"
    assert client.get(asset["contentUrl"]).content == output.getvalue()

    from app.config import get_settings

    with sqlite3.connect(Path(get_settings().database_path)) as connection:
        history = connection.execute(
            "SELECT prompt, provider_kind, model FROM media_generations WHERE asset_id = ?",
            (asset["id"],),
        ).fetchone()
    assert history == (
        "A cyan product launch scene on a black background",
        "openai-images",
        "image-model",
    )
    audit = client.get("/api/state").json()["audit"]
    assert any(item["action"] == "media.generated" and item["entityId"] == asset["id"] for item in audit)


def test_malformed_generated_image_returns_a_validation_error(client, monkeypatch) -> None:
    from app.services.image_generation import GeneratedImage

    malformed_png = __import__("base64").b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFElEQVR4nGP4z8DAwMDAxMDAwMDAAAAJBQEDAAbzXQAAAABJRU5ErkJggg=="
    )

    async def fake_generate(_settings, _request):
        return GeneratedImage(
            data=malformed_png,
            provider_kind="openai-images",
            model="image-model",
            parameters={},
        )

    monkeypatch.setattr("app.main.generate_image", fake_generate)
    rejected = client.post(
        "/api/media/generate",
        json={"prompt": "A malformed provider response for validation"},
    )
    assert rejected.status_code == 400
    assert rejected.json()["error"] == "The image data is not a valid JPEG, PNG, or WebP image."


def test_comfyui_workflow_settings_are_validated_and_preserved(client) -> None:
    workflow = {
        "3": {"class_type": "KSampler", "inputs": {"seed": "{{seed}}", "steps": "{{steps}}"}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "{{prompt}}"}},
        "9": {"class_type": "SaveImage", "inputs": {"images": ["3", 0]}},
    }
    saved = client.put(
        "/api/settings/image-provider",
        json={
            "kind": "comfyui",
            "baseUrl": "http://127.0.0.1:8188/",
            "model": "local-workflow",
            "workflowJson": json.dumps(workflow),
        },
    )
    assert saved.status_code == 200
    public = saved.json()["state"]["imageProvider"]
    assert public["kind"] == "comfyui"
    assert public["baseUrl"] == "http://127.0.0.1:8188"
    assert public["hasWorkflow"] is True
    assert public["configured"] is True
    assert "workflowJson" not in public

    preserved = client.put(
        "/api/settings/image-provider",
        json={
            "kind": "comfyui",
            "baseUrl": "http://127.0.0.1:8188",
            "model": "renamed-workflow",
            "workflowJson": "",
        },
    )
    assert preserved.status_code == 200
    assert preserved.json()["state"]["imageProvider"]["hasWorkflow"] is True

    rejected = client.put(
        "/api/settings/image-provider",
        json={
            "kind": "comfyui",
            "baseUrl": "http://127.0.0.1:8189",
            "model": "",
            "workflowJson": "not-json",
        },
    )
    assert rejected.status_code == 422


def test_comfyui_adapter_injects_placeholders_and_fetches_first_output(monkeypatch) -> None:
    from io import BytesIO

    from PIL import Image

    from app.schemas import ImageGenerateRequest
    from app.services import image_generation

    output = BytesIO()
    Image.new("RGB", (4, 3), color=(139, 92, 246)).save(output, format="PNG")
    calls: list[dict[str, object]] = []

    async def fake_request(url: str, **kwargs):
        calls.append({"url": url, **kwargs})
        if url.endswith("/prompt"):
            return {"prompt_id": "prompt-123", "number": 1}
        if url.endswith("/history/prompt-123"):
            return {
                "prompt-123": {
                    "status": {"status_str": "success"},
                    "outputs": {
                        "9": {
                            "images": [
                                {"filename": "result.png", "subfolder": "socium", "type": "output"}
                            ]
                        }
                    },
                }
            }
        raise AssertionError(f"Unexpected ComfyUI request: {url}")

    async def fake_image(url: str, **kwargs):
        calls.append({"url": url, **kwargs})
        return output.getvalue()

    monkeypatch.setattr(image_generation, "_request_json", fake_request)
    monkeypatch.setattr(image_generation, "_request_image_bytes", fake_image)
    progress: list[tuple[int, str]] = []
    remote_refs: list[str] = []
    generated = asyncio.run(
        image_generation.generate_image(
            {
                "kind": "comfyui",
                "base_url": "http://127.0.0.1:8188",
                "model": "flux-local",
                "api_key": "",
                "workflow_json": json.dumps(
                    {
                        "3": {
                            "class_type": "KSampler",
                            "inputs": {
                                "seed": "{{seed}}",
                                "steps": "{{steps}}",
                                "cfg": "{{guidance_scale}}",
                            },
                        },
                        "5": {
                            "class_type": "EmptyLatentImage",
                            "inputs": {"width": "{{width}}", "height": "{{height}}"},
                        },
                        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "{{prompt}}"}},
                    }
                ),
            },
            ImageGenerateRequest(
                prompt="A local editorial campaign image",
                preset="portrait",
                steps=31,
                guidanceScale=6.5,
                seed=77,
            ),
            progress=lambda percent, message: progress.append((percent, message)),
            remote_ref=remote_refs.append,
        )
    )
    assert generated.data == output.getvalue()
    assert generated.provider_kind == "comfyui"
    assert generated.parameters["promptId"] == "prompt-123"
    assert remote_refs == ["prompt-123"]
    prompt_body = calls[0]["json_body"]["prompt"]
    assert prompt_body["3"]["inputs"] == {"seed": 77, "steps": 31, "cfg": 6.5}
    assert prompt_body["5"]["inputs"] == {"width": 896, "height": 1152}
    assert prompt_body["6"]["inputs"]["text"] == "A local editorial campaign image"
    assert progress[-1][0] == 85
    assert calls[-1]["params"] == {
        "filename": "result.png",
        "subfolder": "socium",
        "type": "output",
    }


def test_comfyui_running_prompt_is_deleted_and_interrupted_on_cancel(monkeypatch) -> None:
    from app.schemas import ImageGenerateRequest
    from app.services import image_generation

    calls: list[dict[str, object]] = []
    cancelled = False

    async def fake_request(url: str, **kwargs):
        nonlocal cancelled
        calls.append({"url": url, **kwargs})
        if url.endswith("/prompt"):
            return {"prompt_id": "prompt-cancel", "number": 1}
        if url.endswith("/queue") and kwargs.get("method") != "POST":
            return {"queue_running": [[1, "prompt-cancel", {}, [], {}]], "queue_pending": []}
        if url.endswith(("/queue", "/interrupt")):
            return {}
        raise AssertionError(f"Unexpected ComfyUI request: {url}")

    def save_remote_ref(_value: str) -> None:
        nonlocal cancelled
        cancelled = True

    monkeypatch.setattr(image_generation, "_request_json", fake_request)
    with pytest.raises(image_generation.GenerationCancelled):
        asyncio.run(
            image_generation.generate_image(
                {
                    "kind": "comfyui",
                    "base_url": "http://127.0.0.1:8188",
                    "model": "",
                    "api_key": "",
                    "workflow_json": json.dumps(
                        {"6": {"class_type": "CLIPTextEncode", "inputs": {"text": "{{prompt}}"}}}
                    ),
                },
                ImageGenerateRequest(prompt="Cancel this running local workflow"),
                cancel_check=lambda: cancelled,
                remote_ref=save_remote_ref,
            )
        )
    queue_delete = next(
        call for call in calls if str(call["url"]).endswith("/queue") and call.get("method") == "POST"
    )
    assert queue_delete["json_body"] == {"delete": ["prompt-cancel"]}
    assert any(str(call["url"]).endswith("/interrupt") for call in calls)


def test_media_generation_runs_through_durable_worker(client, monkeypatch) -> None:
    from io import BytesIO

    from PIL import Image

    from app.database import write_session
    from app.models import LocalJob
    from app.scheduler import LocalScheduler
    from app.services.image_generation import GeneratedImage
    from app.store import utc_now

    configured = client.put(
        "/api/settings/image-provider",
        json={
            "kind": "openai-images",
            "baseUrl": "https://images.example/v1",
            "model": "queue-image-model",
            "apiKey": "secret",
        },
    )
    assert configured.status_code == 200
    assert client.put("/api/scheduler", json={"paused": True}).status_code == 200
    queued = client.post(
        "/api/media/generations",
        json={"prompt": "A durable queued campaign visual", "preset": "landscape"},
    )
    assert queued.status_code == 200
    assert queued.json()["job"]["status"] == "queued"
    assert queued.json()["job"]["progressPercent"] == 0

    output = BytesIO()
    Image.new("RGB", (80, 45), color=(34, 211, 238)).save(output, format="PNG")

    async def fake_generate(_settings, request, **kwargs):
        kwargs["progress"](55, "Provider is generating.")
        return GeneratedImage(
            data=output.getvalue(),
            provider_kind="openai-images",
            model="queue-image-model",
            parameters={"preset": request.preset},
        )

    monkeypatch.setattr("app.scheduler.generate_image", fake_generate)
    with write_session() as session:
        stored_job = session.get(LocalJob, queued.json()["job"]["id"])
        assert stored_job is not None
        stored_job.status = "running"
        stored_job.attempts = 1
        stored_job.locked_at = utc_now()
        stored_job.updated_at = utc_now()
    claimed = client.get("/api/media/generations").json()["items"][0]
    assert claimed["kind"] == "media.generate"
    worker = LocalScheduler(interval=1, catch_up_hours=24, stale_minutes=10)
    asyncio.run(worker._execute(claimed))
    assert client.put("/api/scheduler", json={"paused": False}).status_code == 200

    jobs = client.get("/api/media/generations").json()["items"]
    completed = next(item for item in jobs if item["id"] == queued.json()["job"]["id"])
    assert completed["status"] == "completed"
    assert completed["progressPercent"] == 100
    assert completed["resultRef"]
    assets = client.get("/api/media").json()["items"]
    assert any(item["id"] == completed["resultRef"] for item in assets)


def test_media_generation_can_be_cancelled_and_retried(client) -> None:
    configured = client.put(
        "/api/settings/image-provider",
        json={
            "kind": "automatic1111",
            "baseUrl": "http://127.0.0.1:7860",
            "model": "",
        },
    )
    assert configured.status_code == 200
    assert client.put("/api/scheduler", json={"paused": True}).status_code == 200
    queued = client.post(
        "/api/media/generations",
        json={"prompt": "A cancellable private image generation"},
    ).json()["job"]
    cancelled = client.post(f"/api/media/generations/{queued['id']}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["job"]["status"] == "cancelled"
    changed_provider = client.put(
        "/api/settings/image-provider",
        json={
            "kind": "openai-images",
            "baseUrl": "https://images-v2.example/v1",
            "model": "new-image-model",
            "apiKey": "new-secret",
        },
    )
    assert changed_provider.status_code == 200
    retried = client.post(f"/api/media/generations/{queued['id']}/retry")
    assert retried.status_code == 200
    assert retried.json()["job"]["status"] == "queued"
    assert retried.json()["job"]["attempts"] == 0
    assert retried.json()["job"]["payload"]["provider"]["kind"] == "openai-images"
    assert retried.json()["job"]["payload"]["provider"]["model"] == "new-image-model"
    assert client.put("/api/scheduler", json={"paused": False}).status_code == 200
