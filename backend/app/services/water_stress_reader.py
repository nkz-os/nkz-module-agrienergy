"""Crop-health state reader: water stress index, its fidelity and shade fraction.

Reads the parcel-level ``CropHealthAssessment`` published by crop-health from
Orion-LD. Agrienergy acts only on a fresh ``iot_sensor`` index; shade is
informational and never enters ``biology``.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

ENTITY_TYPE = "CropHealthAssessment"
CACHE_TTL_S = 60.0
MAX_FUTURE_SKEW_S = 300
ACTIONABLE_FIDELITY = "iot_sensor"

_monotonic = time.monotonic
_cache: dict[tuple[str, str], tuple[float, "CropHealthState | None"]] = {}


@dataclass(frozen=True)
class CropHealthState:
    stress_index: float | None
    fidelity: str | None
    observed_at: datetime | None
    shade_fraction: float | None


def reset_cache() -> None:
    """Drop all cached results (test isolation)."""
    _cache.clear()


def _unit_interval(raw: Any) -> float | None:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    val = float(raw)
    if math.isnan(val) or not 0.0 <= val <= 1.0:
        return None
    return val


def _parse_datetime(raw: Any) -> datetime | None:
    if isinstance(raw, dict):
        raw = raw.get("@value", raw.get("value"))
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        ts = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def _to_state(entity: dict) -> CropHealthState:
    fidelity = entity.get("waterStressFidelity")
    return CropHealthState(
        stress_index=_unit_interval(entity.get("waterStressIndex")),
        fidelity=fidelity if isinstance(fidelity, str) and fidelity else None,
        observed_at=_parse_datetime(entity.get("waterStressObservedAt")),
        shade_fraction=_unit_interval(entity.get("shadeFraction")),
    )


def _pick_freshest(entities: list[dict]) -> CropHealthState | None:
    """Max ``waterStressObservedAt``; entities without it rank last.

    The newest id is not necessarily the freshest observation (day rollover).
    """
    best: CropHealthState | None = None
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        state = _to_state(entity)
        if best is None:
            best = state
        elif state.observed_at is not None and (
            best.observed_at is None or state.observed_at > best.observed_at
        ):
            best = state
    return best


async def fetch_crop_health_state(
    orion, tenant_id: str, parcel_urn: str | None
) -> CropHealthState | None:
    if not parcel_urn:
        return None
    key = (tenant_id, parcel_urn)
    now = _monotonic()
    hit = _cache.get(key)
    if hit is not None and now - hit[0] < CACHE_TTL_S:
        return hit[1]
    try:
        entities = await orion.query_entities(
            type=ENTITY_TYPE,
            q=f'hasAgriParcel=="{parcel_urn}"|refAgriParcel=="{parcel_urn}"',
            limit=10,
            options="keyValues",
        )
    except Exception as exc:  # fail-safe: no state means no action; not cached
        logger.warning(
            "crop-health state read failed tenant=%s parcel=%s error=%s",
            tenant_id, parcel_urn, exc,
        )
        return None
    state = _pick_freshest(list(entities or []))
    _cache[key] = (now, state)
    return state


def biology_from_state(
    state: CropHealthState | None, *, max_age_s: int, now: datetime
) -> dict[str, float]:
    """``{"stress_index": x}`` only for a fresh ``iot_sensor`` index, else ``{}``."""
    if state is None or state.fidelity != ACTIONABLE_FIDELITY:
        return {}
    if state.stress_index is None or state.observed_at is None:
        return {}
    age_s = (now - state.observed_at).total_seconds()
    if age_s < -MAX_FUTURE_SKEW_S:
        return {}
    age_s = max(age_s, 0.0)
    if age_s > max_age_s:
        return {}
    return {"stress_index": state.stress_index}
