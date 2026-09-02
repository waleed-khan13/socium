from __future__ import annotations

import os
import re
from dataclasses import dataclass
from ipaddress import ip_address
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from app.errors import ExternalServiceError

DEFAULT_LINKEDIN_API_BASE_URL = "https://api.linkedin.com"
DEFAULT_LINKEDIN_VERSION = "202607"
_LINKEDIN_VERSION_PATTERN = re.compile(r"20\d{4}")
_PERSON_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{2,128}")
_ORGANIZATION_ID_PATTERN = re.compile(r"\d{1,30}")
_POST_URN_PATTERN = re.compile(r"urn:li:(?:share|ugcPost):\d+")


@dataclass(frozen=True, slots=True)
class LinkedInApiResponse:
    payload: dict[str, Any]
    headers: dict[str, str]


@dataclass(frozen=True, slots=True)
class LinkedInPublishResult:
    remote_id: str
    remote_url: str | None = None


def _is_loopback_hostname(hostname: str) -> bool:
    normalized = hostname.lower()
    if normalized == "localhost":
        return True
    try:
        return ip_address(normalized).is_loopback
    except ValueError:
        return False


def validate_linkedin_api_base_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ExternalServiceError("LinkedIn API base URL must be a valid http or https address.")
    if parsed.username or parsed.password:
        raise ExternalServiceError("LinkedIn API base URL must not contain credentials.")
    if parsed.query or parsed.fragment:
        raise ExternalServiceError("LinkedIn API base URL must not contain a query or fragment.")

    hostname = parsed.hostname.lower()
    is_loopback = _is_loopback_hostname(hostname)
    if parsed.scheme != "https" and not is_loopback:
        raise ExternalServiceError(
            "Use HTTPS for LinkedIn. HTTP is allowed only for a localhost test service."
        )
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


def validate_linkedin_version(value: str) -> str:
    version = value.strip()
    if not _LINKEDIN_VERSION_PATTERN.fullmatch(version):
        raise ExternalServiceError("LinkedIn API version must use YYYYMM format, such as 202607.")
    return version


def validate_linkedin_person_id(value: str) -> str:
    person_id = value.strip()
    if not _PERSON_ID_PATTERN.fullmatch(person_id):
        raise ExternalServiceError("LinkedIn Member ID contains unsupported characters.")
    return person_id


def validate_linkedin_organization_id(value: str) -> str:
    organization_id = value.strip()
    if not _ORGANIZATION_ID_PATTERN.fullmatch(organization_id):
        raise ExternalServiceError("LinkedIn Organization ID must contain digits only.")
    return organization_id


def _api_base_url() -> str:
    return validate_linkedin_api_base_url(
        os.getenv("SOCIUM_LINKEDIN_API_BASE_URL", DEFAULT_LINKEDIN_API_BASE_URL)
    )


def _linkedin_error(payload: object, status_code: int) -> str:
    if isinstance(payload, dict):
        message = str(payload.get("message") or "").strip()
        code = str(payload.get("serviceErrorCode") or payload.get("status") or "").strip()
        if message and code:
            return f"LinkedIn API error {code}: {message}"
        if message:
            return f"LinkedIn API: {message}"
    return f"LinkedIn API returned HTTP {status_code}."


async def linkedin_api_request(
    resource: str,
    access_token: str,
    *,
    method: str = "GET",
    api_version: str | None = None,
    json_body: dict[str, Any] | None = None,
    timeout: float = 30,
) -> LinkedInApiResponse:
    token = access_token.strip()
    if not token:
        raise ExternalServiceError("LinkedIn OAuth Access Token is required.")
    endpoint = f"{_api_base_url()}/{resource.lstrip('/')}"
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    }
    if api_version is not None:
        headers.update(
            {
                "Linkedin-Version": validate_linkedin_version(api_version),
                "X-Restli-Protocol-Version": "2.0.0",
                "Content-Type": "application/json",
            }
        )

    try:
        async with httpx.AsyncClient(follow_redirects=False, timeout=timeout) as client:
            response = await client.request(
                method,
                endpoint,
                headers=headers,
                json=json_body,
            )
    except httpx.HTTPError as error:
        raise ExternalServiceError(
            f"LinkedIn request failed ({type(error).__name__})."
        ) from error

    payload: object = {}
    if response.content:
        try:
            payload = response.json()
        except ValueError as error:
            if response.is_success:
                raise ExternalServiceError(
                    f"LinkedIn API returned a non-JSON response ({response.status_code})."
                ) from error
    if not response.is_success:
        message = _linkedin_error(payload, response.status_code).replace(token, "[redacted]")
        raise ExternalServiceError(message)
    if not isinstance(payload, dict):
        raise ExternalServiceError("LinkedIn API returned an invalid JSON object.")
    return LinkedInApiResponse(payload=payload, headers=dict(response.headers))


async def test_linkedin_connection(
    person_id: str,
    access_token: str,
) -> dict[str, str]:
    expected_person_id = validate_linkedin_person_id(person_id)
    response = await linkedin_api_request("v2/userinfo", access_token, timeout=15)
    remote_person_id = str(response.payload.get("sub") or "").strip()
    if not remote_person_id:
        raise ExternalServiceError("LinkedIn did not return a Member ID from userinfo.")
    if remote_person_id != expected_person_id:
        raise ExternalServiceError("The OAuth token belongs to a different LinkedIn member.")
    return {
        "personId": remote_person_id,
        "name": str(response.payload.get("name") or "LinkedIn Member").strip(),
    }


async def test_linkedin_organization_connection(
    person_id: str,
    organization_id: str,
    api_version: str,
    access_token: str,
) -> dict[str, str]:
    member = await test_linkedin_connection(person_id, access_token)
    verified_organization_id = validate_linkedin_organization_id(organization_id)
    person_urn = f"urn:li:person:{member['personId']}"
    organization_urn = f"urn:li:organization:{verified_organization_id}"
    encoded_person_urn = person_urn.replace(":", "%3A")
    encoded_organization_urn = organization_urn.replace(":", "%3A")
    resource = (
        "rest/organizationAuthorizations/"
        f"(impersonator:{encoded_person_urn},organization:{encoded_organization_urn},"
        "action:(organizationContentAuthorizationAction:(actionType:ORGANIC_SHARE_CREATE)))"
    )
    response = await linkedin_api_request(
        resource,
        access_token,
        api_version=api_version,
        timeout=20,
    )
    status = response.payload.get("status")
    approved = isinstance(status, dict) and any(
        str(key).endswith(".Approved") for key in status
    )
    if not approved:
        raise ExternalServiceError(
            "This member is not authorized to create organic posts for that LinkedIn Page."
        )
    remote_person_urn = str(response.payload.get("impersonator") or "").strip()
    remote_organization_urn = str(response.payload.get("organization") or "").strip()
    if remote_person_urn != person_urn or remote_organization_urn != organization_urn:
        raise ExternalServiceError(
            "LinkedIn returned organization authorization for a different member or Page."
        )
    return {
        **member,
        "organizationId": verified_organization_id,
        "organizationUrn": organization_urn,
        "authorization": "ORGANIC_SHARE_CREATE",
    }


def approved_linkedin_commentary(post: dict[str, Any]) -> str:
    body = str(post.get("body") or "").strip()
    hashtags = [
        f"#{tag}"
        for value in post.get("hashtags") or []
        if (tag := str(value).strip().lstrip("#"))
    ]
    commentary = "\n\n".join(part for part in (body, " ".join(hashtags)) if part)
    if not commentary:
        raise ExternalServiceError("The approved LinkedIn post is empty.")
    if len(commentary) > 3_000:
        raise ExternalServiceError("LinkedIn text posts must not exceed 3,000 characters.")
    return commentary


async def upload_linkedin_image(
    author: str,
    api_version: str,
    access_token: str,
    media: dict[str, Any],
) -> str:
    initialized = await linkedin_api_request(
        "rest/images?action=initializeUpload",
        access_token,
        method="POST",
        api_version=api_version,
        json_body={"initializeUploadRequest": {"owner": author}},
        timeout=30,
    )
    value = initialized.payload.get("value")
    if not isinstance(value, dict):
        raise ExternalServiceError("LinkedIn did not initialize the image upload.")
    upload_url = str(value.get("uploadUrl") or "")
    image_urn = str(value.get("image") or "")
    parsed = urlsplit(upload_url)
    hostname = (parsed.hostname or "").lower()
    api_base = urlsplit(_api_base_url())
    local_test_upload = (
        _is_loopback_hostname(api_base.hostname or "")
        and hostname == (api_base.hostname or "").lower()
        and parsed.port == api_base.port
        and parsed.scheme in {"http", "https"}
    )
    if (
        not (
            parsed.scheme == "https"
            and (hostname == "linkedin.com" or hostname.endswith(".linkedin.com"))
        )
        and not local_test_upload
    ) or (
        parsed.username
        or parsed.password
        or parsed.fragment
        or not image_urn.startswith("urn:li:image:")
    ):
        raise ExternalServiceError("LinkedIn returned an invalid image upload destination.")
    try:
        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=httpx.Timeout(60, connect=10),
        ) as client:
            response = await client.put(
                upload_url,
                content=media["data"],
                headers={
                    "Authorization": f"Bearer {access_token.strip()}",
                    "Content-Type": media["mimeType"],
                },
            )
    except httpx.HTTPError as error:
        raise ExternalServiceError("Could not upload the approved image to LinkedIn.") from error
    if not response.is_success:
        raise ExternalServiceError(f"LinkedIn image upload returned HTTP {response.status_code}.")
    return image_urn


async def _linkedin_post_body(
    author: str,
    api_version: str,
    access_token: str,
    post: dict[str, Any],
    media: dict[str, Any] | None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "author": author,
        "commentary": approved_linkedin_commentary(post),
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }
    if media is not None:
        image_urn = await upload_linkedin_image(
            author, api_version, access_token, media
        )
        body["content"] = {
            "media": {
                "id": image_urn,
                "altText": str(post.get("imageAltText") or media.get("altText") or "")[:4_086],
            }
        }
    return body


async def publish_linkedin_member_post(
    person_id: str,
    api_version: str,
    access_token: str,
    post: dict[str, Any],
    media: dict[str, Any] | None = None,
) -> LinkedInPublishResult:
    author = f"urn:li:person:{validate_linkedin_person_id(person_id)}"
    body = await _linkedin_post_body(author, api_version, access_token, post, media)
    response = await linkedin_api_request(
        "rest/posts",
        access_token,
        method="POST",
        api_version=api_version,
        json_body=body,
        timeout=45,
    )
    remote_id = str(
        response.headers.get("x-restli-id") or response.payload.get("id") or ""
    ).strip()
    if not _POST_URN_PATTERN.fullmatch(remote_id):
        raise ExternalServiceError("LinkedIn did not return a valid published post URN.")
    return LinkedInPublishResult(remote_id=remote_id)


async def publish_linkedin_organization_post(
    organization_id: str,
    api_version: str,
    access_token: str,
    post: dict[str, Any],
    media: dict[str, Any] | None = None,
) -> LinkedInPublishResult:
    author = f"urn:li:organization:{validate_linkedin_organization_id(organization_id)}"
    body = await _linkedin_post_body(author, api_version, access_token, post, media)
    response = await linkedin_api_request(
        "rest/posts",
        access_token,
        method="POST",
        api_version=api_version,
        json_body=body,
        timeout=45,
    )
    remote_id = str(
        response.headers.get("x-restli-id") or response.payload.get("id") or ""
    ).strip()
    if not _POST_URN_PATTERN.fullmatch(remote_id):
        raise ExternalServiceError("LinkedIn did not return a valid published post URN.")
    return LinkedInPublishResult(remote_id=remote_id)
