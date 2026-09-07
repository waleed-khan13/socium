from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta


def test_lead_import_normalizes_company_and_contact_without_breaking_lead_api(client) -> None:
    email = "growth-normalized@socium.test"
    imported = client.post(
        "/api/leads/import",
        json={
            "source": "csv",
            "rows": [
                {
                    "businessName": "Growth Normalized Studio",
                    "website": "https://growth-normalized.socium.test/about",
                    "email": email,
                    "phone": "+92 300 555 0101",
                    "location": "Karachi",
                    "sourceRef": "licensed-export-row-1",
                    "notes": "User-owned provider export.",
                }
            ],
        },
    )
    assert imported.status_code == 200

    leads = client.get("/api/leads", params={"query": email}).json()["items"]
    assert len(leads) == 1
    assert leads[0]["companyId"]
    assert leads[0]["contactId"]

    growth = client.get("/api/growth")
    assert growth.status_code == 200
    company = next(item for item in growth.json()["companies"] if item["id"] == leads[0]["companyId"])
    contact = next(item for item in growth.json()["contacts"] if item["id"] == leads[0]["contactId"])
    assert company["domain"] == "growth-normalized.socium.test"
    assert company["contactCount"] == 1
    assert contact["email"] == email
    assert contact["companyName"] == "Growth Normalized Studio"

    deleted = client.request(
        "DELETE",
        f"/api/leads/{leads[0]['id']}",
        json={"reason": "Verify normalized privacy cleanup.", "confirmation": "DELETE"},
    )
    assert deleted.status_code == 200
    growth_after_delete = client.get("/api/growth").json()
    assert all(item["id"] != contact["id"] for item in growth_after_delete["contacts"])
    assert all(item["id"] != company["id"] for item in growth_after_delete["companies"])


def test_campaign_prepares_review_draft_and_real_reply_stops_member(client) -> None:
    email = "campaign-reply@socium.test"
    client.post(
        "/api/leads/import",
        json={
            "source": "manual",
            "rows": [
                {
                    "businessName": "Campaign Reply Company",
                    "website": "https://campaign-reply.socium.test",
                    "email": email,
                    "location": "Lahore",
                    "notes": "Existing customer relationship.",
                }
            ],
        },
    )
    lead = client.get("/api/leads", params={"query": email}).json()["items"][0]
    retention = (datetime.now(UTC).date() + timedelta(days=90)).isoformat()
    reviewed = client.put(
        f"/api/leads/{lead['id']}/compliance",
        json={
            "consentStatus": "not_applicable",
            "legalBasis": "existing_customer",
            "legalBasisNote": "Existing customer asked for relevant product updates.",
            "retentionUntil": retention,
        },
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["lead"]["outreachReady"] is True

    created = client.post(
        "/api/growth/campaigns",
        json={
            "name": "Customer follow-up",
            "objective": "Share a useful account update",
            "tone": "Clear and respectful",
            "leadIds": [lead["id"]],
            "steps": [
                {
                    "waitDays": 0,
                    "subjectTemplate": "An update for {{business_name}}",
                    "bodyTemplate": "Hello {{business_name}}, see {{website}} for context.",
                },
                {
                    "waitDays": 0,
                    "subjectTemplate": "Re: An update for {{business_name}}",
                    "bodyTemplate": "Following up once, then this sequence stops.",
                },
            ],
            "stopOnReply": True,
            "stopOnConsentChange": True,
        },
    )
    assert created.status_code == 200
    campaign = created.json()["campaign"]
    assert campaign["status"] == "draft"
    assert campaign["members"][0]["status"] == "pending"

    activated = client.patch(
        f"/api/growth/campaigns/{campaign['id']}", json={"status": "active"}
    )
    assert activated.status_code == 200
    member = activated.json()["campaign"]["members"][0]
    assert member["status"] == "awaiting_approval"
    assert member["lastDraftId"]

    drafts = client.get(f"/api/leads/{lead['id']}/outreach-drafts").json()["items"]
    campaign_draft = next(item for item in drafts if item["id"] == member["lastDraftId"])
    assert campaign_draft["status"] == "draft"
    assert campaign_draft["subject"] == "An update for Campaign Reply Company"

    approved = client.post(
        f"/api/outreach-drafts/{campaign_draft['id']}/decision",
        json={"decision": "approve", "revision": 1},
    )
    assert approved.status_code == 200
    exported = client.post(
        f"/api/outreach-drafts/{campaign_draft['id']}/export", json={"revision": 1}
    )
    assert exported.status_code == 200
    current = next(
        item
        for item in client.get("/api/growth").json()["campaigns"]
        if item["id"] == campaign["id"]
    )["members"][0]
    if current["status"] == "waiting":
        from app.growth_store import prepare_due_campaign_step

        prepare_due_campaign_step(current["id"])
        current = next(
            item
            for item in client.get("/api/growth").json()["campaigns"]
            if item["id"] == campaign["id"]
        )["members"][0]
    assert current["status"] == "awaiting_approval"
    assert current["currentStep"] == 1
    assert current["lastDraftId"] != campaign_draft["id"]

    from app.growth_store import stop_campaign_members_for_reply

    assert stop_campaign_members_for_reply(email) == 1
    stopped = next(
        item for item in client.get("/api/growth").json()["campaigns"] if item["id"] == campaign["id"]
    )["members"][0]
    assert stopped["status"] == "stopped"
    assert stopped["stopReason"] == "Reply received in Gmail."

    # A scheduler job already leased during the reply race becomes a safe no-op
    # instead of retrying a campaign that was intentionally stopped.
    from app.growth_store import prepare_due_campaign_step

    assert prepare_due_campaign_step(stopped["id"]) == stopped["id"]


def test_lead_provider_manifests_are_declarative_and_strict(client) -> None:
    from app.config import get_settings

    directory = get_settings().data_dir / "plugins" / "lead-providers"
    directory.mkdir(parents=True, exist_ok=True)
    manifest = directory / "licensed-fixture.json"
    manifest.write_text(
        json.dumps(
            {
                "id": "licensed-fixture",
                "displayName": "Licensed Fixture",
                "license": "Customer-owned test license",
                "homepageUrl": "https://provider.socium.test",
                "importFormat": "csv",
                "fields": ["business_name", "email", "password", "session_cookie"],
            }
        ),
        encoding="utf-8",
    )
    try:
        response = client.get("/api/lead-providers")
        assert response.status_code == 200
        provider = next(item for item in response.json()["providers"] if item["id"] == "licensed-fixture")
        assert provider["fields"] == ["business_name", "email"]
        assert response.json()["executionPolicy"].startswith("Import-only")
    finally:
        manifest.unlink(missing_ok=True)
