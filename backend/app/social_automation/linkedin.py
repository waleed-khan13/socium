from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from typing import Any
from urllib.parse import urljoin, urlsplit

from app.social_automation.contracts import Authentication, AuthState, BrowserError, BrowserResult


def commentary(post: dict[str, Any]) -> str:
    body = str(post.get("body") or "").strip()
    tags = ["#" + str(tag).lstrip("#") for tag in post.get("hashtags", []) if str(tag).strip()]
    tags = [tag for tag in tags if tag not in body]
    return body + ("\n\n" + " ".join(dict.fromkeys(tags)) if tags else "")


def profile_identity(href: str) -> str | None:
    url = urlsplit(urljoin("https://www.linkedin.com", href))
    if url.scheme != "https" or url.hostname != "www.linkedin.com":
        return None
    match = re.fullmatch(r"/in/([^/]+)/?", url.path)
    return f"https://www.linkedin.com/in/{match[1]}/" if match else None


class LinkedInAdapter:
    platform = "linkedin"
    version = "linkedin-member-0.1"
    login_url = "https://www.linkedin.com/feed/"

    async def _confirmation_links(self, page: Any) -> set[str]:
        links: set[str] = set()
        for item in await page.locator('[role="alert"] a[href*="/feed/update/"]').all():
            url = urlsplit(urljoin(self.login_url, await item.get_attribute("href") or ""))
            if (
                url.scheme == "https"
                and url.hostname == "www.linkedin.com"
                and re.fullmatch(r"/feed/update/urn:li:activity:\d+/?", url.path)
            ):
                links.add(f"https://www.linkedin.com{url.path.rstrip('/')}/")
        return links

    async def authenticate(self, page: Any) -> Authentication:
        location = urlsplit(page.url)
        if location.scheme != "https" or location.hostname != "www.linkedin.com":
            return Authentication(AuthState.UNKNOWN)
        path = location.path.lower()
        if any(part in path for part in ("checkpoint", "challenge", "captcha")):
            return Authentication(AuthState.VERIFICATION_REQUIRED)
        if any(part in path for part in ("login", "uas/", "signup")):
            return Authentication(AuthState.NOT_AUTHENTICATED)
        if await page.locator('input[type="password"]').count():
            return Authentication(AuthState.NOT_AUTHENTICATED)
        # Only the signed-in identity in navigation/profile summary, never a feed author's link.
        links = page.locator(
            'nav a[href*="/in/"], .profile-card a[href*="/in/"], .feed-identity-module a[href*="/in/"]'
        )
        if not await page.get_by_role("button", name=re.compile(r"^Start a post", re.IGNORECASE)).count():
            return Authentication(AuthState.UNKNOWN)
        for link in await links.all():
            identity = profile_identity(await link.get_attribute("href") or "")
            if identity and await link.is_visible():
                return Authentication(AuthState.AUTHENTICATED, identity)
        return Authentication(AuthState.UNKNOWN)

    def validate(self, post: dict[str, Any], media: dict[str, Any] | None) -> None:
        if post.get("channel") != "linkedin" or not str(post.get("body") or "").strip():
            raise BrowserError(
                "UNSUPPORTED_CONTENT", "This adapter supports LinkedIn member text and one image only."
            )
        if len(commentary(post)) > 3000:
            raise BrowserError(
                "CONTENT_TOO_LONG", "Shorten the LinkedIn post and hashtags to 3,000 characters."
            )
        if media and (
            media["mimeType"] not in {"image/png", "image/jpeg", "image/webp"}
            or len(media["data"]) > 10 * 1024 * 1024
        ):
            raise BrowserError("UNSUPPORTED_MEDIA", "Use one PNG, JPEG or WebP image up to 10 MB.")
        if post.get("mediaUrl") and not media:
            raise BrowserError(
                "LOCAL_MEDIA_REQUIRED",
                "Import this image into the Media Library first; browser publishing cannot silently omit an external image.",
            )

    async def _evidence(self, page: Any, text: str, identity: str, require_image: bool = False) -> set[str]:
        results: set[str] = set()
        # A success toast or a closed composer is not enough to prove publication.
        for card in await page.locator('.feed-shared-update-v2, [data-urn^="urn:li:activity:"]').all():
            if " ".join(text.split()) not in " ".join((await card.inner_text()).split()):
                continue
            authors = card.locator(
                '.update-components-actor a[href*="/in/"], .feed-shared-actor a[href*="/in/"]'
            )
            if not any(
                [
                    profile_identity(await link.get_attribute("href") or "") == identity
                    for link in await authors.all()
                ]
            ):
                continue
            if (
                require_image
                and not await card.locator(
                    ".update-components-image__image, .feed-shared-image__image"
                ).count()
            ):
                continue
            urn = await card.get_attribute("data-urn") or ""
            if re.fullmatch(r"urn:li:activity:\d+", urn):
                results.add(f"https://www.linkedin.com/feed/update/{urn}/")
        return results

    async def publish(
        self, page: Any, post: dict[str, Any], media: dict[str, Any] | None, before_click: Callable[[], None]
    ) -> BrowserResult:
        text = commentary(post)
        previous = await self._evidence(page, text, post["browserAccountIdentity"], bool(media))
        previous_confirmations = await self._confirmation_links(page)
        await page.get_by_role("button", name=re.compile(r"^Start a post", re.IGNORECASE)).click()
        dialog = page.get_by_role("dialog")
        await dialog.wait_for(state="visible")
        editor = dialog.locator(
            '[role="textbox"][contenteditable="true"], .ql-editor[contenteditable="true"]'
        )
        await editor.fill(text)
        if media:
            await dialog.get_by_role(
                "button", name=re.compile(r"^(Add media|Add a photo|Add photos|Photo)$", re.IGNORECASE)
            ).click()
            await page.locator('input[type="file"]').set_input_files(
                {
                    "name": media["filename"],
                    "mimeType": media["mimeType"],
                    "buffer": media["data"],
                }
            )
            next_button = page.get_by_role("dialog").get_by_role("button", name="Next", exact=True)
            if await next_button.count():
                await next_button.click()
            # Never publish a requested image as text-only if the upload UI changed.
            await dialog.locator('img[src^="blob:"], img[src*="media.licdn.com"]').first.wait_for(
                state="visible"
            )
            if media.get("altText"):
                alt_button = dialog.get_by_role("button", name=re.compile(r"alt text", re.IGNORECASE))
                if not await alt_button.count():
                    raise BrowserError(
                        "SELECTOR_CHANGED", "Image alt-text control was not found. Nothing was published."
                    )
                await alt_button.click()
                await page.get_by_role("textbox", name=re.compile(r"alt text", re.IGNORECASE)).fill(
                    media["altText"]
                )
                await page.get_by_role("button", name="Save", exact=True).click()
        button = dialog.get_by_role("button", name="Post", exact=True)
        if not await button.is_enabled():
            raise BrowserError(
                "COMPOSER_NOT_READY", "LinkedIn has not enabled publishing. Review your content."
            )
        before_click()
        await button.click()  # Exactly one attempt; persisted intent precedes this call.
        for _ in range(15):
            links = await self._evidence(page, text, post["browserAccountIdentity"], bool(media))
            confirmations = await self._confirmation_links(page)
            fresh = (links - previous) & (confirmations - previous_confirmations)
            if len(fresh) == 1:
                url = fresh.pop()
                return BrowserResult(url.rstrip("/").split("/")[-1], url)
            await asyncio.sleep(1)
        raise BrowserError(
            "PUBLISH_UNCERTAIN",
            "LinkedIn may have published this post. Check your profile before taking further action.",
            uncertain=True,
        )
