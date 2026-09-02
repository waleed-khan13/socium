from __future__ import annotations

import asyncio
import json
import re
import socket
from dataclasses import dataclass
from html.parser import HTMLParser
from ipaddress import ip_address
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx

from app.errors import AppError, ExternalServiceError

ROBOTS_USER_AGENT = "Socium"
USER_AGENT = "Socium/0.9 (+https://github.com/waleed-khan13/socium)"
MAX_PAGE_BYTES = 1_000_000
MAX_PAGES = 4
CRAWL_LOCK = asyncio.Lock()
CONTACT_HINTS = ("contact", "about", "team", "company", "reach", "connect")
BRAND_HINTS = ("about", "services", "products", "solutions", "work", "company")
HEX_COLOR_PATTERN = re.compile(r"#[0-9a-fA-F]{6}\b")
FONT_FAMILY_PATTERN = re.compile(r"font-family\s*:\s*([^;}]+)", re.IGNORECASE)
TAILWIND_SANS_PATTERN = re.compile(
    r"(?:sans|heading|body|display)\s*:\s*\[\s*['\"]+\"?"
    r"([A-Za-z][A-Za-z0-9 ]{1,48})\"?['\"]+",
    re.IGNORECASE,
)
EMAIL_PATTERN = re.compile(
    r"(?<![\w.+-])([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})(?![\w.-])",
    re.IGNORECASE,
)
PHONE_PATTERN = re.compile(r"(?<!\w)(\+?\d[\d\s().-]{6,}\d)(?!\w)")


@dataclass(frozen=True)
class CrawlResponse:
    final_url: str
    status_code: int
    content_type: str
    headers: dict[str, str]
    content: bytes


def _clean_text(value: str) -> str:
    return " ".join(value.split()).strip()


def _unique(values: list[str], limit: int = 10) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        clean = _clean_text(value)
        key = clean.casefold()
        if clean and key not in seen:
            seen.add(key)
            output.append(clean)
        if len(output) >= limit:
            break
    return output


def _address_text(value: object) -> str:
    if isinstance(value, str):
        return _clean_text(value)
    if not isinstance(value, dict):
        return ""
    keys = ("streetAddress", "addressLocality", "addressRegion", "postalCode", "addressCountry")
    return ", ".join(_clean_text(str(value[key])) for key in keys if value.get(key))


def _json_ld_objects(value: object) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        objects = [value]
        graph = value.get("@graph")
        if isinstance(graph, list):
            objects.extend(item for item in graph if isinstance(item, dict))
        return objects
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


class PageExtractor(HTMLParser):
    _VOID_TAGS = frozenset(
        {
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "param",
            "source",
            "track",
            "wbr",
        }
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.h1 = ""
        self.description = ""
        self.site_name = ""
        self.links: list[str] = []
        self.emails: list[str] = []
        self.phones: list[str] = []
        self.business_names: list[str] = []
        self.locations: list[str] = []
        self.logo_candidates: list[str] = []
        self.colors: list[str] = []
        self.fonts: list[str] = []
        self.social_links: list[str] = []
        self._capture: str | None = None
        self._buffer: list[str] = []
        self._json_ld = False
        self._visible_text: list[str] = []
        self._element_stack: list[tuple[str, bool]] = []
        self._brand_region_depth = 0
        self._hidden_content_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key.casefold(): value or "" for key, value in attrs}
        lowered = tag.casefold()
        region_identity = " ".join(
            (
                attributes.get("class", ""),
                attributes.get("id", ""),
                attributes.get("role", ""),
            )
        ).casefold()
        starts_brand_region = (
            lowered in {"header", "footer"}
            or attributes.get("role", "").casefold() in {"banner", "contentinfo"}
            or any(
                hint in region_identity
                for hint in ("site-header", "page-header", "site-footer", "page-footer")
            )
        )
        if lowered not in self._VOID_TAGS:
            self._element_stack.append((lowered, starts_brand_region))
            if starts_brand_region:
                self._brand_region_depth += 1
        if lowered in {"script", "style", "noscript", "svg", "template"}:
            self._hidden_content_depth += 1

        if lowered in {"title", "h1"}:
            self._capture = lowered
            self._buffer = []
        elif lowered == "script" and attributes.get("type", "").casefold() == "application/ld+json":
            self._json_ld = True
            self._capture = "json-ld"
            self._buffer = []
        elif lowered == "meta":
            name = (attributes.get("name") or attributes.get("property") or "").casefold()
            content = _clean_text(attributes.get("content", ""))
            if name in {"description", "og:description"} and content and not self.description:
                self.description = content
            if name == "og:site_name" and content:
                self.site_name = content
            if name == "theme-color" and HEX_COLOR_PATTERN.fullmatch(content):
                self.colors.append(content)
        elif lowered == "a":
            href = attributes.get("href", "").strip()
            if href:
                self.links.append(href)
                scheme = urlsplit(href).scheme.casefold()
                if scheme == "mailto":
                    self.emails.append(href.split(":", 1)[1].split("?", 1)[0])
                elif scheme == "tel":
                    self.phones.append(href.split(":", 1)[1].split("?", 1)[0])
                if any(
                    domain in href.casefold()
                    for domain in (
                        "linkedin.com",
                        "instagram.com",
                        "facebook.com",
                        "x.com",
                        "twitter.com",
                        "youtube.com",
                    )
                ):
                    self.social_links.append(href)
        elif lowered == "img":
            identity = " ".join(
                (
                    attributes.get("alt", ""),
                    attributes.get("aria-label", ""),
                    attributes.get("class", ""),
                    attributes.get("id", ""),
                    attributes.get("src", ""),
                    attributes.get("data-src", ""),
                )
            ).casefold()
            source = (attributes.get("src") or attributes.get("data-src") or "").strip()
            if source and self._brand_region_depth > 0 and ("logo" in identity or "brand" in identity):
                self.logo_candidates.append(source)

        style = attributes.get("style", "")
        if style:
            self.colors.extend(HEX_COLOR_PATTERN.findall(style))
            self.fonts.extend(_font_names(style))

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.casefold()
        if self._capture == lowered:
            value = _clean_text(" ".join(self._buffer))
            if lowered == "title" and not self.title:
                self.title = value
            elif lowered == "h1" and not self.h1:
                self.h1 = value
            self._capture = None
            self._buffer = []
        elif lowered == "script" and self._json_ld:
            raw = "".join(self._buffer).strip()
            self._capture = None
            self._buffer = []
            self._json_ld = False
            try:
                payload = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                payload = None
            if payload is not None:
                for item in _json_ld_objects(payload):
                    kind = item.get("@type")
                    kinds = {str(value) for value in kind} if isinstance(kind, list) else {str(kind)}
                    if kinds & {"Organization", "LocalBusiness", "ProfessionalService", "Corporation"}:
                        if item.get("name"):
                            self.business_names.append(str(item["name"]))
                        if item.get("email"):
                            self.emails.append(str(item["email"]).removeprefix("mailto:"))
                        if item.get("telephone"):
                            self.phones.append(str(item["telephone"]))
                        address = _address_text(item.get("address"))
                        if address:
                            self.locations.append(address)
        if lowered in {"script", "style", "noscript", "svg", "template"}:
            self._hidden_content_depth = max(0, self._hidden_content_depth - 1)
        for index in range(len(self._element_stack) - 1, -1, -1):
            if self._element_stack[index][0] != lowered:
                continue
            removed = self._element_stack[index:]
            del self._element_stack[index:]
            self._brand_region_depth = max(
                0,
                self._brand_region_depth - sum(1 for _, starts_region in removed if starts_region),
            )
            break

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._buffer.append(data)
        elif self._hidden_content_depth == 0 and _clean_text(data):
            self._visible_text.append(data)
        if self._capture != "json-ld":
            self.colors.extend(HEX_COLOR_PATTERN.findall(data))
            self.fonts.extend(_font_names(data))
            self.fonts.extend(TAILWIND_SANS_PATTERN.findall(data))

    def result(self) -> dict[str, object]:
        visible = _clean_text(" ".join(self._visible_text))[:200_000]
        emails = self.emails + [match.group(1) for match in EMAIL_PATTERN.finditer(visible)]
        phones = self.phones + [match.group(1) for match in PHONE_PATTERN.finditer(visible)]
        return {
            "title": self.title,
            "h1": self.h1,
            "description": self.description,
            "siteName": self.site_name,
            "links": self.links,
            "emails": _unique(emails),
            "phones": _unique(phones),
            "businessNames": _unique(self.business_names),
            "locations": _unique(self.locations),
            "visibleText": visible[:12_000],
            "logoCandidates": _unique(self.logo_candidates, 10),
            "colors": _unique([value.lower() for value in self.colors], 12),
            "fonts": _unique(self.fonts, 8),
            "socialLinks": _unique(self.social_links, 12),
        }


def _font_names(value: str) -> list[str]:
    output: list[str] = []
    for match in FONT_FAMILY_PATTERN.finditer(value):
        for raw in match.group(1).split(","):
            name = raw.strip().strip("'\"")
            if name and name.casefold() not in {
                "inherit",
                "initial",
                "sans-serif",
                "serif",
                "monospace",
                "system-ui",
            }:
                output.append(name[:160])
    return output


def normalize_website_url(value: str) -> str:
    raw = value.strip()
    if "://" not in raw:
        raw = f"https://{raw}"
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError as error:
        raise AppError("Website URL is invalid.") from error
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
        raise AppError("Website URL must use http or https.")
    if parsed.username or parsed.password:
        raise AppError("Website URL must not contain credentials.")
    hostname = parsed.hostname.casefold().rstrip(".")
    netloc = hostname if port is None else f"{hostname}:{port}"
    return urlunsplit((parsed.scheme.casefold(), netloc, parsed.path or "/", parsed.query, ""))


async def validate_public_url(value: str) -> str:
    url = normalize_website_url(value)
    hostname = urlsplit(url).hostname or ""
    try:
        records = await asyncio.to_thread(socket.getaddrinfo, hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror as error:
        raise AppError("Website hostname could not be resolved.") from error
    addresses = {record[4][0] for record in records}
    if not addresses or any(not ip_address(address).is_global for address in addresses):
        raise AppError("Website must resolve only to public internet addresses.")
    return url


async def read_public_page(
    client: httpx.AsyncClient,
    url: str,
    *,
    accepted_types: tuple[str, ...],
    max_bytes: int,
) -> CrawlResponse:
    current = url
    for _redirect in range(4):
        current = await validate_public_url(current)
        try:
            async with client.stream("GET", current, headers={"User-Agent": USER_AGENT}) as response:
                if response.is_redirect:
                    location = response.headers.get("location", "")
                    if not location:
                        raise ExternalServiceError("Website returned an invalid redirect.")
                    target = urljoin(current, location)
                    if not _same_site(url, target):
                        raise ExternalServiceError(
                            "Website redirected to a different domain; crawl stopped safely."
                        )
                    current = target
                    continue
                content_type = response.headers.get("content-type", "").split(";", 1)[0].casefold()
                headers = {key.casefold(): value for key, value in response.headers.items()}
                if response.status_code >= 400:
                    return CrawlResponse(current, response.status_code, content_type, headers, b"")
                if content_type and not any(content_type.startswith(item) for item in accepted_types):
                    raise ExternalServiceError(f"Website returned unsupported content type {content_type}.")
                declared = int(response.headers.get("content-length", "0") or 0)
                if declared > max_bytes:
                    raise ExternalServiceError("Website page is larger than the crawler safety limit.")
                chunks: list[bytes] = []
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > max_bytes:
                        raise ExternalServiceError("Website page is larger than the crawler safety limit.")
                    chunks.append(chunk)
                return CrawlResponse(
                    current,
                    response.status_code,
                    content_type,
                    headers,
                    b"".join(chunks),
                )
        except httpx.HTTPError as error:
            raise ExternalServiceError(f"Website request failed ({type(error).__name__}).") from error
    raise ExternalServiceError("Website redirected too many times.")


async def _read_response(
    client: httpx.AsyncClient,
    url: str,
    *,
    accepted_types: tuple[str, ...],
    max_bytes: int,
) -> tuple[str, int, str, bytes]:
    response = await read_public_page(
        client,
        url,
        accepted_types=accepted_types,
        max_bytes=max_bytes,
    )
    return response.final_url, response.status_code, response.content_type, response.content


async def _robots(client: httpx.AsyncClient, target_url: str) -> tuple[RobotFileParser, float]:
    parsed = urlsplit(target_url)
    robots_url = urlunsplit((parsed.scheme, parsed.netloc, "/robots.txt", "", ""))
    final_url, status, _content_type, content = await _read_response(
        client,
        robots_url,
        accepted_types=("text/plain", "text/html", "application/octet-stream"),
        max_bytes=250_000,
    )
    parser = RobotFileParser()
    parser.set_url(final_url)
    if status in {401, 403}:
        parser.parse(["User-agent: *", "Disallow: /"])
    elif status >= 500:
        raise ExternalServiceError("Website robots.txt is temporarily unavailable; crawl stopped safely.")
    elif content:
        parser.parse(content.decode("utf-8", errors="replace").splitlines())
    else:
        parser.parse([])
    delay = parser.crawl_delay(ROBOTS_USER_AGENT) or parser.crawl_delay("*") or 0.5
    return parser, min(max(float(delay), 0.25), 5.0)


async def robots_policy(client: httpx.AsyncClient, target_url: str) -> tuple[RobotFileParser, float]:
    return await _robots(client, target_url)


def _same_site(first: str, second: str) -> bool:
    left = (urlsplit(first).hostname or "").casefold().removeprefix("www.")
    right = (urlsplit(second).hostname or "").casefold().removeprefix("www.")
    return bool(left and left == right)


def _contact_urls(page_url: str, links: list[str]) -> list[str]:
    ranked: list[tuple[int, str]] = []
    seen: set[str] = set()
    for raw in links:
        candidate = urljoin(page_url, raw)
        parsed = urlsplit(candidate)
        if parsed.scheme not in {"http", "https"} or not _same_site(page_url, candidate):
            continue
        clean = urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", parsed.query, ""))
        if clean in seen:
            continue
        lowered = f"{parsed.path} {parsed.query}".casefold()
        matches = [index for index, hint in enumerate(CONTACT_HINTS) if hint in lowered]
        if matches:
            seen.add(clean)
            ranked.append((min(matches), clean))
    return [url for _rank, url in sorted(ranked)[: MAX_PAGES - 1]]


def _brand_urls(page_url: str, links: list[str]) -> list[str]:
    ranked: list[tuple[int, str]] = []
    seen: set[str] = set()
    for raw in links:
        candidate = urljoin(page_url, raw)
        parsed = urlsplit(candidate)
        if parsed.scheme not in {"http", "https"} or not _same_site(page_url, candidate):
            continue
        clean = urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", parsed.query, ""))
        lowered = f"{parsed.path} {parsed.query}".casefold()
        matches = [index for index, hint in enumerate(BRAND_HINTS) if hint in lowered]
        if clean not in seen and matches:
            seen.add(clean)
            ranked.append((min(matches), clean))
    return [url for _rank, url in sorted(ranked)[: MAX_PAGES - 1]]


def _fallback_business_name(page: dict[str, object], hostname: str) -> str:
    for key in ("businessNames", "siteName"):
        value = page.get(key)
        if isinstance(value, list) and value:
            return str(value[0])[:200]
        if isinstance(value, str) and value:
            return value[:200]
    for key in ("h1", "title"):
        value = str(page.get(key) or "")
        if value:
            return re.split(r"\s+[|—–-]\s+", value, maxsplit=1)[0][:200]
    return hostname.removeprefix("www.")[:200]


async def crawl_website(value: str) -> dict[str, object]:
    async with CRAWL_LOCK:
        return await _crawl_website(value)


async def _crawl_website(value: str) -> dict[str, object]:
    start_url = await validate_public_url(value)
    timeout = httpx.Timeout(15, connect=8)
    pages: list[dict[str, object]] = []
    emails: list[str] = []
    phones: list[str] = []
    locations: list[str] = []
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        robots, delay = await _robots(client, start_url)
        queue = [start_url]
        visited: set[str] = set()
        while queue and len(pages) < MAX_PAGES:
            url = queue.pop(0)
            if url in visited:
                continue
            visited.add(url)
            if not robots.can_fetch(ROBOTS_USER_AGENT, url):
                if not pages:
                    raise AppError("Website robots.txt does not allow this page to be crawled.", 403)
                continue
            if pages:
                await asyncio.sleep(delay)
            final_url, status, _content_type, content = await _read_response(
                client,
                url,
                accepted_types=("text/html", "application/xhtml+xml"),
                max_bytes=MAX_PAGE_BYTES,
            )
            if status >= 400:
                if not pages:
                    raise ExternalServiceError(f"Website returned HTTP {status}.")
                continue
            extractor = PageExtractor()
            extractor.feed(content.decode("utf-8", errors="replace"))
            result = extractor.result()
            result["url"] = final_url
            pages.append(result)
            emails.extend(str(item) for item in result["emails"] if isinstance(item, str))
            phones.extend(str(item) for item in result["phones"] if isinstance(item, str))
            locations.extend(str(item) for item in result["locations"] if isinstance(item, str))
            if len(pages) == 1:
                queue.extend(_contact_urls(final_url, [str(item) for item in result["links"]]))

    if not pages:
        raise ExternalServiceError("Website did not return a crawlable HTML page.")
    canonical_url = str(pages[0]["url"])
    hostname = urlsplit(canonical_url).hostname or ""
    description = next((str(page["description"]) for page in pages if page.get("description")), "")
    return {
        "businessName": _fallback_business_name(pages[0], hostname),
        "website": canonical_url,
        "email": (_unique(emails, 1) or [""])[0],
        "phone": (_unique(phones, 1) or [""])[0],
        "location": (_unique(locations, 1) or [""])[0],
        "sourceRef": canonical_url,
        "notes": description[:1_000],
        "pages": [
            {"url": str(page["url"]), "title": str(page.get("title") or page.get("h1") or "")}
            for page in pages
        ],
        "robotsRespected": True,
        "userAgent": USER_AGENT,
    }


async def crawl_brand_website(value: str) -> dict[str, object]:
    """Return bounded, public brand evidence without persisting website content."""
    async with CRAWL_LOCK:
        start_url = await validate_public_url(value)
        timeout = httpx.Timeout(15, connect=8)
        pages: list[dict[str, object]] = []
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            robots, delay = await _robots(client, start_url)
            queue = [start_url]
            visited: set[str] = set()
            while queue and len(pages) < MAX_PAGES:
                url = queue.pop(0)
                if url in visited:
                    continue
                visited.add(url)
                if not robots.can_fetch(ROBOTS_USER_AGENT, url):
                    if not pages:
                        raise AppError("Website robots.txt does not allow this page to be crawled.", 403)
                    continue
                if pages:
                    await asyncio.sleep(delay)
                final_url, status, _content_type, content = await _read_response(
                    client,
                    url,
                    accepted_types=("text/html", "application/xhtml+xml"),
                    max_bytes=MAX_PAGE_BYTES,
                )
                if status >= 400:
                    if not pages:
                        raise ExternalServiceError(f"Website returned HTTP {status}.")
                    continue
                extractor = PageExtractor()
                extractor.feed(content.decode("utf-8", errors="replace"))
                result = extractor.result()
                result["url"] = final_url
                result["logoCandidates"] = [
                    urljoin(final_url, str(candidate))
                    for candidate in result["logoCandidates"]
                    if urlsplit(urljoin(final_url, str(candidate))).scheme in {"http", "https"}
                ]
                pages.append(result)
                if len(pages) == 1:
                    queue.extend(_brand_urls(final_url, [str(item) for item in result["links"]]))

        if not pages:
            raise ExternalServiceError("Website did not return a crawlable HTML page.")
        canonical_url = str(pages[0]["url"])
        hostname = urlsplit(canonical_url).hostname or ""
        return {
            "businessName": _fallback_business_name(pages[0], hostname),
            "website": canonical_url,
            "location": next((str(item) for page in pages for item in page["locations"]), ""),
            "description": next((str(page["description"]) for page in pages if page.get("description")), ""),
            "colors": _unique([str(item) for page in pages for item in page["colors"]], 12),
            "fonts": _unique([str(item) for page in pages for item in page["fonts"]], 8),
            "logoCandidates": _unique([str(item) for page in pages for item in page["logoCandidates"]], 10),
            "socialLinks": _unique([str(item) for page in pages for item in page["socialLinks"]], 12),
            "pages": [
                {
                    "url": str(page["url"]),
                    "title": str(page.get("title") or page.get("h1") or ""),
                    "description": str(page.get("description") or "")[:1_000],
                    "text": str(page.get("visibleText") or "")[:6_000],
                }
                for page in pages
            ],
            "robotsRespected": True,
            "userAgent": USER_AGENT,
        }


async def download_public_brand_image(value: str) -> CrawlResponse:
    """Download one explicitly discovered public raster image within the media safety limit."""
    timeout = httpx.Timeout(15, connect=8)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        return await read_public_page(
            client,
            value,
            accepted_types=("image/jpeg", "image/png", "image/webp"),
            max_bytes=10 * 1024 * 1024,
        )
