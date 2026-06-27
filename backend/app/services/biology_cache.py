"""Biology scalar bundle — push-read from tracker ``biologyCache`` (Intelligence worker)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_MAX_AGE_S = 300


def _parse_cache(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    if isinstance(raw, dict) and "value" in raw:
        raw = raw["value"]
    if not isinstance(raw, dict):
        return None
    return raw


def read_biology_cache(tracker: dict) -> dict[str, float]:
    """Extract scalar biology metrics from tracker ``biologyCache`` Property."""
    cache = _parse_cache(tracker.get("biologyCache"))
    if not cache:
        return {}

    scalars = cache.get("scalars") if isinstance(cache.get("scalars"), dict) else cache
    out: dict[str, float] = {}
    for key, val in scalars.items():
        if key in ("updatedAt", "source", "tracker_id"):
            continue
        if isinstance(val, (int, float)):
            out[key] = float(val)
    return out


def is_biology_cache_fresh(tracker: dict, max_age_s: int = DEFAULT_MAX_AGE_S) -> bool:
    cache = _parse_cache(tracker.get("biologyCache"))
    if not cache:
        return False
    updated = cache.get("updatedAt") or cache.get("updated_at")
    if not updated:
        return False
    try:
        ts = datetime.fromisoformat(str(updated).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - ts).total_seconds()
        return age <= max_age_s
    except (TypeError, ValueError):
        return False


async def resolve_biology_context(
    tracker: dict,
    intelligence_client,
    *,
    tenant_id: str,
    tracker_id: str,
    parcel_id: str,
    timestamp: str,
    shadow_polygon_2d: list,
    telemetry: dict,
    max_age_s: int = DEFAULT_MAX_AGE_S,
) -> dict[str, float]:
    """Prefer push cache; pull from Intelligence only when stale or missing."""
    if is_biology_cache_fresh(tracker, max_age_s):
        cached = read_biology_cache(tracker)
        if cached:
            logger.debug("biology: cache hit tracker=%s keys=%s", tracker_id, list(cached))
            return cached

    pulled = await intelligence_client.evaluate_status(
        tenant_id=tenant_id,
        tracker_id=tracker_id,
        parcel_id=parcel_id,
        timestamp=timestamp,
        shadow_polygon_2d=shadow_polygon_2d,
        telemetry=telemetry,
    )
    return pulled if pulled else read_biology_cache(tracker)
