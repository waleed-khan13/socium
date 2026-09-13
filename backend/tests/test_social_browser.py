from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, select

from app.database import read_session, write_session
from app.errors import AppError
from app.models import BrowserPublishAttempt, LocalJob, Post, SocialBrowserAccount
from app.social_automation import manager
from app.social_automation.browser import exclusive_browser, profile_path
from app.social_automation.contracts import (
    AccountCreate,
    Authentication,
    AuthState,
    BrowserError,
    BrowserResult,
)
from app.social_automation.linkedin import LinkedInAdapter, commentary, profile_identity
from app.social_automation.store import (
    account_by_id,
    cancel_operation,
    claim_attempt,
    create_account,
    finish_attempt,
    mark_click_intent,
    public_state,
    queue_operation,
    record_auth,
    recover_interrupted_attempts,
    set_preferred,
)
from app.store import create_post, decide_post, initialize_storage, reserve_publish


@pytest.fixture(autouse=True)
def browser_records():
    initialize_storage()
    yield
    with write_session() as session:
        post_ids = set(session.scalars(select(Post.id).where(Post.topic == "browser-test")))
        for job in session.scalars(select(LocalJob).where(LocalJob.kind == "post.publish")):
            if job.payload.get("post_id") in post_ids:
                session.delete(job)
        session.execute(delete(BrowserPublishAttempt))
        session.execute(delete(LocalJob).where(LocalJob.kind.like("social.%")))
        session.execute(delete(Post).where(Post.topic == "browser-test"))
        session.execute(delete(SocialBrowserAccount))


def account(name="Test LinkedIn", slug="test-member"):
    result = create_account(AccountCreate(platform="linkedin", name=name, acknowledge_policy_risk=True))
    record_auth(result["id"], Authentication(AuthState.AUTHENTICATED, f"https://www.linkedin.com/in/{slug}/"))
    set_preferred(result["id"])
    return account_by_id(result["id"])


def draft():
    return create_post(
        request={"topic": "browser-test", "channel": "linkedin", "tone": "Clear", "objective": "Test"},
        content={
            "title": "A verified post",
            "body": "Useful local business context.",
            "hashtags": ["Socium"],
        },
        provider={"kind": "ollama", "model": "fixture"},
    )


def reserved():
    result = draft()
    decide_post(result["id"], result["revision"], "approve")
    return reserve_publish(result["id"], result["revision"])


def test_consent_and_platform_validation():
    with pytest.raises(BrowserError, match="risk"):
        create_account(AccountCreate(platform="linkedin", name="Personal", acknowledge_policy_risk=False))
    with pytest.raises(ValueError):
        AccountCreate(platform="instagram", name="Not ready", acknowledge_policy_risk=True)


def test_old_posts_stay_api_and_new_posts_freeze_destination():
    old = draft()
    first = account()
    new = draft()
    second = account("Other profile", "other-member")
    assert old["browserAccountId"] is None
    assert new["browserAccountId"] == first["id"]
    assert new["browserAccountIdentity"] == first["identity"]
    assert draft()["browserAccountId"] == second["id"]
    assert not account_by_id(first["id"])["preferred"]


def test_reconnect_cannot_change_identity():
    connected = account()
    record_auth(
        connected["id"], Authentication(AuthState.AUTHENTICATED, "https://www.linkedin.com/in/someone-else/")
    )
    changed = account_by_id(connected["id"])
    assert changed["identity"] == connected["identity"]
    assert changed["status"] == "requires_verification"
    assert changed["lastErrorCode"] == "ACCOUNT_CHANGED"


def test_session_expiry_does_not_fall_back_to_api():
    connected = account()
    record_auth(connected["id"], Authentication(AuthState.NOT_AUTHENTICATED))
    with pytest.raises(AppError, match="Reconnect"):
        draft()


def test_publish_attempt_is_exact_revision_and_one_shot():
    account()
    post = reserved()
    attempt = claim_attempt(post, "fixture")
    with pytest.raises(BrowserError, match="already has"):
        claim_attempt(post, "fixture")
    mark_click_intent(attempt)
    finish_attempt(attempt, error_code="TIMEOUT")
    assert public_state()["attempts"][0]["status"] == "uncertain"
    with pytest.raises(BrowserError) as captured:
        claim_attempt(post, "fixture")
    assert captured.value.uncertain


def test_safe_preflight_failure_allows_explicit_retry():
    account()
    post = reserved()
    attempt = claim_attempt(post, "fixture")
    finish_attempt(attempt, error_code="AUTH_REQUIRED")
    assert claim_attempt(post, "fixture") == attempt


def test_final_click_rechecks_approval_and_account():
    connected = account()
    post = reserved()
    attempt = claim_attempt(post, "fixture")
    record_auth(connected["id"], Authentication(AuthState.NOT_AUTHENTICATED))
    with pytest.raises(BrowserError, match="Approval changed"):
        mark_click_intent(attempt)


def test_parallel_claims_have_only_one_winner():
    from concurrent.futures import ThreadPoolExecutor

    account()
    post = reserved()

    def claim():
        try:
            claim_attempt(post, "fixture")
            return "claimed"
        except BrowserError:
            return "blocked"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: claim(), range(2))) == ["blocked", "claimed"]


def test_restart_cancels_login_without_reopening_a_window():
    connected = account()
    queue_operation("social.connect", connected["id"])
    recover_interrupted_attempts()
    assert public_state()["jobs"][0]["status"] == "cancelled"


def test_interrupted_intent_requires_review():
    account()
    post = reserved()
    attempt = claim_attempt(post, "fixture")
    mark_click_intent(attempt)
    recover_interrupted_attempts()
    assert public_state()["attempts"][0]["status"] == "uncertain"
    with pytest.raises(BrowserError):
        claim_attempt(post, "fixture")


def test_profile_isolation_lock_and_traversal():
    first, second = account(), account("Second", "second")
    assert profile_path(first["id"]) != profile_path(second["id"])
    with pytest.raises(BrowserError):
        profile_path("../../Chrome/User Data")
    with exclusive_browser(), pytest.raises(BrowserError, match="Another browser"), exclusive_browser():
        pass
    with exclusive_browser():
        pass  # OS lock released even after a failed second acquisition.


def test_disconnect_removes_only_selected_session():
    first, second = account(), account("Second", "second")
    first_path, second_path = profile_path(first["id"]), profile_path(second["id"])
    first_path.mkdir(parents=True)
    second_path.mkdir(parents=True)
    manager.disconnect(first["id"])
    assert not first_path.exists() and second_path.exists()
    assert account_by_id(first["id"])["status"] == "disconnected"
    assert account_by_id(first["id"])["identity"] == first["identity"]


def test_setup_jobs_deduplicate_cancel_and_hide_private_paths():
    connected = account()
    first = queue_operation("social.connect", connected["id"])
    assert queue_operation("social.connect", connected["id"])["id"] == first["id"]
    cancel_operation(first["id"])
    assert public_state()["jobs"][0]["status"] == "cancelled"
    serialized = json.dumps(public_state()).lower()
    assert (
        "cookie" not in serialized and "browser_profiles" not in serialized and "password" not in serialized
    )


@pytest.mark.parametrize(
    "href",
    [
        "https://evil.test/in/person/",
        "http://www.linkedin.com/in/person/",
        "https://www.linkedin.com.evil.test/in/person/",
    ],
)
def test_profile_identity_rejects_other_origins(href):
    assert profile_identity(href) is None


def test_content_validation_and_normalized_hashtags():
    adapter = LinkedInAdapter()
    assert (
        commentary({"body": "Hello #Socium", "hashtags": ["Socium", "Local", "#Local"]})
        == "Hello #Socium\n\n#Local"
    )
    with pytest.raises(BrowserError):
        adapter.validate({"channel": "linkedin", "body": "x" * 3001}, None)
    with pytest.raises(BrowserError):
        adapter.validate(
            {"channel": "linkedin", "body": "Hello", "mediaUrl": "https://example.test/photo.png"}, None
        )


@pytest.mark.parametrize("after_click", [False, True])
def test_manager_sanitizes_errors_and_records_uncertainty(monkeypatch, after_click):
    connected = account()
    post = reserved()

    class Adapter:
        version = "fixture"
        login_url = "https://www.linkedin.com/feed/"

        def validate(self, *_args):
            pass

        async def authenticate(self, _page):
            return Authentication(AuthState.AUTHENTICATED, connected["identity"])

        async def publish(self, _page, _post, _media, before_click):
            if after_click:
                before_click()
            raise RuntimeError("secret-cookie-and-private-profile-path")

    class Page:
        async def goto(self, *_args, **_kwargs):
            pass

    @asynccontextmanager
    async def fake_browser(*_args, **_kwargs):
        yield Page()

    monkeypatch.setattr(manager, "open_browser", fake_browser)
    monkeypatch.setattr(manager, "get_adapter", lambda _: Adapter())
    with pytest.raises(BrowserError) as caught:
        asyncio.run(manager.publish(post, None))
    assert caught.value.uncertain == after_click
    assert "secret-cookie" not in str(caught.value)
    assert public_state()["attempts"][0]["status"] == ("uncertain" if after_click else "safe_failed")


def _fake_publish_browser(monkeypatch, adapter):
    class Page:
        async def goto(self, *_args, **_kwargs):
            pass

    @asynccontextmanager
    async def fake_browser(*_args, **_kwargs):
        yield Page()

    monkeypatch.setattr(manager, "open_browser", fake_browser)
    monkeypatch.setattr(manager, "get_adapter", lambda _: adapter)
    monkeypatch.setattr(manager, "AUTH_SETTLE_SECONDS", 0)


def test_publish_waits_for_slow_feed_before_checking_session(monkeypatch):
    connected = account()
    post = reserved()
    checks = []

    class Adapter:
        version = "fixture"
        login_url = "https://www.linkedin.com/feed/"

        def validate(self, *_args):
            pass

        async def authenticate(self, _page):
            checks.append(True)
            if len(checks) < 3:
                return Authentication(AuthState.UNKNOWN)
            return Authentication(AuthState.AUTHENTICATED, connected["identity"])

        async def publish(self, _page, _post, _media, before_click):
            before_click()
            return BrowserResult("urn:li:activity:1", "https://www.linkedin.com/feed/update/urn:li:activity:1/")

    _fake_publish_browser(monkeypatch, Adapter())
    assert asyncio.run(manager.publish(post, None)).remote_id == "urn:li:activity:1"
    assert len(checks) == 3
    assert account_by_id(connected["id"])["status"] == "connected"


def test_unsettled_page_does_not_demote_connected_account(monkeypatch):
    connected = account()
    post = reserved()

    class Adapter:
        version = "fixture"
        login_url = "https://www.linkedin.com/feed/"

        def validate(self, *_args):
            pass

        async def authenticate(self, _page):
            return Authentication(AuthState.UNKNOWN)

        async def publish(self, *_args):
            raise AssertionError("publish must not run without a confirmed session")

    _fake_publish_browser(monkeypatch, Adapter())
    with pytest.raises(BrowserError, match="Nothing was published") as caught:
        asyncio.run(manager.publish(post, None))
    assert not caught.value.uncertain
    assert account_by_id(connected["id"])["status"] == "connected"
    assert public_state()["attempts"][0]["status"] == "safe_failed"


def test_publish_keeps_media_library_alt_text_when_post_has_none(monkeypatch):
    connected = account()
    post = {**reserved(), "imageAltText": ""}
    received = []

    class Adapter:
        version = "fixture"
        login_url = "https://www.linkedin.com/feed/"

        def validate(self, *_args):
            pass

        async def authenticate(self, _page):
            return Authentication(AuthState.AUTHENTICATED, connected["identity"])

        async def publish(self, _page, _post, media, before_click):
            received.append(media)
            before_click()
            return BrowserResult("urn:li:activity:2", "https://www.linkedin.com/feed/update/urn:li:activity:2/")

    _fake_publish_browser(monkeypatch, Adapter())
    media = {"filename": "a.png", "mimeType": "image/png", "data": b"png", "altText": "Library description"}
    asyncio.run(manager.publish(post, media))
    assert received[0]["altText"] == "Library description"


def test_restart_releases_interrupted_browser_install():
    job = queue_operation("social.browser.install")
    with write_session() as session:
        item = session.get(LocalJob, job["id"])
        item.status = "running"
        item.lease_token = "dead-worker"
    recover_interrupted_attempts()
    installs = [item for item in public_state()["jobs"] if item["id"] == job["id"]]
    assert installs[0]["status"] == "cancelled"
    assert queue_operation("social.browser.install")["id"] != job["id"]


def test_duplicate_channels_reserve_only_once():
    account()
    post = draft()
    decide_post(post["id"], 1, "approve", "slack")
    with pytest.raises(AppError):
        decide_post(post["id"], 1, "approve", "telegram")
    reserve_publish(post["id"], 1)
    with pytest.raises(AppError):
        reserve_publish(post["id"], 1)


def test_scheduler_browser_publish_uses_frozen_account(monkeypatch):
    from datetime import datetime

    from app.scheduler import LocalScheduler
    from app.schemas import SchedulePostRequest
    from app.store import schedule_post, utc_now

    connected = account()
    post = draft()
    decide_post(post["id"], 1, "approve")
    scheduled, _ = schedule_post(
        post["id"], SchedulePostRequest(revision=1, run_at=datetime.fromisoformat(utc_now())), 24
    )
    with write_session() as session:
        item = session.get(LocalJob, scheduled["id"])
        item.status = "running"
        job = {"id": item.id, "kind": item.kind, "payload": item.payload}
    calls = []

    async def fake_publish(snapshot, _media):
        calls.append(snapshot)
        return BrowserResult(
            "urn:li:activity:123", "https://www.linkedin.com/feed/update/urn:li:activity:123/"
        )

    monkeypatch.setattr(manager, "publish", fake_publish)
    scheduler = LocalScheduler(0.1, 24, 10)
    asyncio.run(scheduler._execute(job))
    assert len(calls) == 1 and calls[0]["browserAccountId"] == connected["id"]
    with read_session() as session:
        assert session.get(Post, post["id"]).status == "published"


def test_authentication_rejects_external_page():
    assert (
        asyncio.run(LinkedInAdapter().authenticate(SimpleNamespace(url="https://evil.test/feed/"))).state
        == AuthState.UNKNOWN
    )


def test_router_returns_queued_jobs_immediately_without_secrets():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.social_automation.routes import create_router

    wake_calls = []
    api = FastAPI()
    api.include_router(create_router(lambda: wake_calls.append(True)))
    with TestClient(api) as client:
        created = client.post(
            "/api/social-browser/accounts",
            json={
                "name": "UI account",
                "platform": "linkedin",
                "acknowledge_policy_risk": True,
            },
        )
        assert created.status_code == 201
        account_id = created.json()["account"]["id"]
        response = client.post(f"/api/social-browser/accounts/{account_id}/connect")
        assert response.status_code == 202 and response.json()["job"]["status"] == "queued"
        assert len(wake_calls) == 1
        body = client.get("/api/social-browser").json()
        assert "browserInstalled" in body and "profilePath" not in body["accounts"][0]
        assert (
            client.post(f"/api/social-browser/jobs/{response.json()['job']['id']}/cancel").status_code == 200
        )


@pytest.mark.parametrize("with_image", [False, True])
def test_real_browser_fixture_verifies_new_post_without_network(monkeypatch, with_image):
    """Exercise actual Playwright selectors on a fully intercepted local fixture, not LinkedIn."""
    from playwright.async_api import async_playwright

    html = """<!doctype html><html lang='en'><body>
    <nav><a href='/in/test-member/'>My profile</a></nav>
    <button onclick="document.querySelector('[role=dialog]').hidden=false">Start a post</button>
    <div role='dialog' hidden><div role='textbox' contenteditable='true'></div>
    <button>Add media</button>
    <input type='file' onchange="document.querySelector('#preview').src=window.URL.createObjectURL(this.files[0]);document.querySelector('#preview').hidden=false">
    <img id='preview' width='32' height='32' hidden>
    <button>Add alt text</button><input id='image-alt' aria-label='Alt text'><button onclick="window.imageAlt=document.getElementById('image-alt').value">Save</button>
    <button onclick="publishFixture()">Post</button></div>
    <script>
    window.postClicks=0;
    function publishFixture(){window.postClicks++;
      const card=document.createElement('article');card.className='feed-shared-update-v2';
      card.dataset.urn='urn:li:activity:999123';
      const actor=document.createElement('div');actor.className='update-components-actor';
      const author=document.createElement('a');author.href='/in/test-member/';author.textContent='Me';
      actor.append(author);card.append(actor);
      const content=document.createElement('p');content.textContent=document.querySelector('[role=textbox]').innerText;
      card.append(content);document.body.append(card);document.querySelector('[role=dialog]').hidden=true;
      if(document.querySelector('#preview').src){const image=document.querySelector('#preview').cloneNode();image.className='update-components-image__image';card.append(image);}
      const confirmation=document.createElement('div');confirmation.setAttribute('role','alert');
      const permalink=document.createElement('a');permalink.href='/feed/update/urn:li:activity:999123/';permalink.textContent='View post';confirmation.append(permalink);document.body.append(confirmation);
    }
    </script></body></html>"""

    async def exercise():
        async with async_playwright() as driver:
            # Uses the test/developer Playwright cache, never a real user's browser profile.
            browser = await driver.chromium.launch(channel="chromium", headless=True)
            try:
                context = await browser.new_context()
                await context.route(
                    "**/*", lambda route: route.fulfill(status=200, content_type="text/html", body=html)
                )
                page = await context.new_page()
                fixture_errors = []
                page.on("pageerror", lambda error: fixture_errors.append(str(error)))
                await page.goto("https://www.linkedin.com/feed/")
                adapter = LinkedInAdapter()
                assert (
                    await adapter.authenticate(page)
                ).identity == "https://www.linkedin.com/in/test-member/"
                intents = []
                import base64

                media = (
                    {
                        "filename": "fixture.png",
                        "mimeType": "image/png",
                        "altText": "A small fixture image",
                        "data": base64.b64decode(
                            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aX2kAAAAASUVORK5CYII="
                        ),
                    }
                    if with_image
                    else None
                )
                try:
                    result = await adapter.publish(
                        page,
                        {
                            "body": "Useful business facts.",
                            "hashtags": ["Socium"],
                            "browserAccountIdentity": "https://www.linkedin.com/in/test-member/",
                        },
                        media,
                        lambda: intents.append(True),
                    )
                except Exception as error:
                    raise AssertionError({"errors": fixture_errors, "html": await page.content()}) from error
                assert result.remote_id == "urn:li:activity:999123"
                assert len(intents) == 1 and await page.evaluate("window.postClicks") == 1
                if with_image:
                    assert await page.evaluate("window.imageAlt") == "A small fixture image"
                await page.goto("https://www.linkedin.com/checkpoint/challenge/")
                assert (await adapter.authenticate(page)).state == AuthState.VERIFICATION_REQUIRED
            finally:
                await browser.close()

    monkeypatch.delenv("PLAYWRIGHT_BROWSERS_PATH", raising=False)
    asyncio.run(exercise())
