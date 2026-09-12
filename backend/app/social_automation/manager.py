from __future__ import annotations

import asyncio
from typing import Any

from app.social_automation.browser import install_browser, open_browser, remove_profile
from app.social_automation.contracts import Authentication, AuthState, BrowserError, BrowserResult
from app.social_automation.registry import get_adapter
from app.social_automation.store import (
    account_by_id,
    claim_attempt,
    finish_attempt,
    mark_click_intent,
    record_auth,
    update_progress,
)


async def run_operation(job: dict[str, Any]) -> None:
    def progress(message: str, percent: int) -> None:
        update_progress(str(job["id"]), message, percent)

    if job["kind"] == "social.browser.install":
        await install_browser(progress)
        return
    account_id = str(job.get("payload", {}).get("account_id") or "")
    account = account_by_id(account_id)
    adapter = get_adapter(account["platform"])
    visible = job["kind"] == "social.connect"
    progress("Opening the dedicated browser. Log in yourself; Socium never asks for your password.", 10)
    try:
        async with open_browser(account_id, visible=visible) as page:
            await page.goto(adapter.login_url, wait_until="domcontentloaded")
            auth = Authentication(AuthState.UNKNOWN)
            for _ in range(180 if visible else 10):
                progress(
                    "Complete login or verification in the browser window."
                    if visible
                    else "Checking saved session.",
                    30,
                )
                auth = await adapter.authenticate(page)
                if auth.state == AuthState.AUTHENTICATED:
                    record_auth(account_id, auth)
                    if account_by_id(account_id)["status"] != "connected":
                        raise BrowserError(
                            "ACCOUNT_CHANGED",
                            "This profile belongs to another account. Create a separate browser account instead.",
                        )
                    progress("Account verified. Select it for future LinkedIn drafts when ready.", 100)
                    return
                await asyncio.sleep(1)
            record_auth(account_id, auth, "AUTH_REQUIRED")
            raise BrowserError(
                "AUTH_REQUIRED",
                "Login was not confirmed. Open login again and complete any verification yourself. English LinkedIn UI is required by this initial adapter.",
            )
    except BrowserError:
        raise
    except Exception as error:
        # Raw browser exceptions can contain page text, URLs or private profile paths.
        record_auth(account_id, Authentication(AuthState.UNKNOWN), "BROWSER_FAILED")
        raise BrowserError(
            "BROWSER_FAILED",
            "Browser could not finish. Check the browser installation, network, and whether the login window was closed.",
        ) from error


async def publish(post: dict[str, Any], media: dict[str, Any] | None) -> BrowserResult:
    if media:
        media = {**media, "altText": str(post.get("imageAltText") or "")}
    account = account_by_id(str(post.get("browserAccountId") or ""))
    adapter = get_adapter(account["platform"])
    adapter.validate(post, media)
    attempt_id: str | None = None
    clicked = False

    def before_click() -> None:
        nonlocal clicked
        assert attempt_id is not None
        mark_click_intent(attempt_id)
        clicked = True

    try:
        async with open_browser(account["id"]) as page:
            attempt_id = claim_attempt(post, adapter.version)
            await page.goto(adapter.login_url, wait_until="domcontentloaded")
            auth = await adapter.authenticate(page)
            record_auth(account["id"], auth)
            if auth.state != AuthState.AUTHENTICATED or auth.identity != post.get("browserAccountIdentity"):
                raise BrowserError(
                    "AUTH_REQUIRED",
                    "Reconnect the exact account approved for this post. Nothing was published.",
                )
            result = await adapter.publish(page, post, media, before_click)
            finish_attempt(attempt_id, remote_url=result.remote_url)
            return result
    except asyncio.CancelledError:
        if attempt_id:
            finish_attempt(attempt_id, error_code="INTERRUPTED")
        raise
    except Exception as error:
        if attempt_id:
            finish_attempt(
                attempt_id, error_code=error.code if isinstance(error, BrowserError) else "BROWSER_FAILED"
            )
        if isinstance(error, BrowserError):
            error.uncertain = error.uncertain or clicked
            raise
        raise BrowserError(
            "PUBLISH_UNCERTAIN" if clicked else "BROWSER_FAILED",
            "Publication could not be verified. Check LinkedIn before doing anything else."
            if clicked
            else "Browser stopped before publishing. LinkedIn may have changed its page; verify the session and retry manually.",
            uncertain=clicked,
        ) from error


def disconnect(account_id: str) -> None:
    from app.database import write_session
    from app.models import SocialBrowserAccount
    from app.store import utc_now

    account_by_id(account_id)

    def forget() -> None:
        with write_session() as session:
            account = session.get(SocialBrowserAccount, account_id)
            account.status = "disconnected"
            account.preferred = False
            account.updated_at = utc_now()

    remove_profile(account_id, forget)
