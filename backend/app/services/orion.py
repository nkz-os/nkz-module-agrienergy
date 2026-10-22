"""
Thin adapter over nkz-platform-sdk OrionClient.

ALL Orion-LD I/O in this module goes through the SDK: tenant travels AS-IS
(hyphen-canonical platform convention) and attribute fragments go as
application/json + Link at library level. Never instantiate httpx against
Orion-LD directly.
"""

from typing import Any, Optional

import httpx
from nkz_platform_sdk.orion import OrionClient

from app.config import get_settings


def _strip_ngsi_path(url: str) -> str:
    """settings.context_broker_url historically includes /ngsi-ld/v1; the SDK
    expects the broker root and appends the path itself."""
    if not url:
        return ""
    return url.rstrip("/").removesuffix("/ngsi-ld/v1")


def get_orion(tenant_id: str) -> OrionClient:
    settings = get_settings()
    return OrionClient(
        tenant_id,
        base_url=_strip_ngsi_path(settings.context_broker_url) or None,
        context_url=settings.context_url or None,
    )


def prop(value: Any) -> dict:
    return {"type": "Property", "value": value}


def rel(target: str) -> dict:
    return {"type": "Relationship", "object": target}


def resolve_device_ref(entity: dict) -> str | None:
    """Resolve a tracker's device URN from hasDevice, falling back to refDevice.

    `hasDevice` is the SDM relationship and the platform standard; `refDevice` is
    the deprecated ref<Type> Property. This module only reads the attribute — the
    writer lives with whatever provisions the tracker — so both spellings have to
    work until every writer has moved (Expand and Contract).

    Accepts the normalized forms (`object` for a Relationship, `value` for a
    Property) and the flat string that options=keyValues returns.
    """
    for attr in ("hasDevice", "refDevice"):
        raw = entity.get(attr)
        if isinstance(raw, dict):
            raw = raw.get("object") if "object" in raw else raw.get("value")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None


async def get_entity_or_none(client: OrionClient, entity_id: str) -> Optional[dict]:
    """404 -> None; other HTTP errors propagate (callers decide 502 vs skip)."""
    try:
        return await client.get_entity(entity_id)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return None
        raise
