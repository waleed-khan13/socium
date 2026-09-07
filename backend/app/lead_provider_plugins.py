from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from app.config import get_settings

CONTRACT_VERSION = "1.0"
PROVIDER_ID = re.compile(r"^[a-z][a-z0-9-]{1,79}$")
ALLOWED_FORMATS = {"csv", "json"}
ALLOWED_FIELDS = {
    "business_name", "website", "email", "phone", "location", "source_ref", "notes",
    "full_name", "job_title",
}


@runtime_checkable
class LicensedLeadProvider(Protocol):
    """Import-only provider boundary. Plugins never receive Socium vault secrets."""

    provider_id: str

    def import_records(self, source_file: Path) -> list[dict[str, str]]: ...


def _manifest_directory() -> Path:
    return get_settings().data_dir / "plugins" / "lead-providers"


def _validate_manifest(value: Any, source: Path) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    provider_id = str(value.get("id", "")).strip()
    display_name = str(value.get("displayName", "")).strip()
    license_name = str(value.get("license", "")).strip()
    homepage_url = str(value.get("homepageUrl", "")).strip()
    import_format = str(value.get("importFormat", "")).strip().lower()
    fields = value.get("fields")
    if (
        not PROVIDER_ID.fullmatch(provider_id)
        or not display_name
        or not license_name
        or not homepage_url.startswith("https://")
        or import_format not in ALLOWED_FORMATS
        or not isinstance(fields, list)
    ):
        return None
    clean_fields = list(dict.fromkeys(str(field) for field in fields if str(field) in ALLOWED_FIELDS))
    if not clean_fields:
        return None
    return {
        "id": provider_id,
        "displayName": display_name[:120],
        "license": license_name[:120],
        "homepageUrl": homepage_url[:2048],
        "importFormat": import_format,
        "fields": clean_fields,
        "installed": True,
        "manifestPath": source.name,
    }


def lead_provider_state() -> dict[str, Any]:
    directory = _manifest_directory()
    providers: list[dict[str, Any]] = []
    if directory.is_dir():
        for path in sorted(directory.glob("*.json")):
            try:
                manifest = _validate_manifest(json.loads(path.read_text(encoding="utf-8")), path)
            except (OSError, UnicodeError, json.JSONDecodeError):
                manifest = None
            if manifest is not None:
                providers.append(manifest)
    return {
        "contractVersion": CONTRACT_VERSION,
        "providers": providers,
        "pluginDirectory": str(directory),
        "executionPolicy": "Import-only; no provider code is executed by the API process.",
    }
