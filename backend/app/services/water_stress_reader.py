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
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Producer id contract (crop-health): one parcel-level assessment per UTC day,
# id ``urn:ngsi-ld:CropHealthAssessment:{parcel_id}-{YYYYMMDD}`` where
# ``parcel_id`` is the AgriParcel URN without its prefix. Fetched by id (a
# type query is unordered and pages out after a few days of history). If the
# producer contract changes, the fetch misses and this fails safe: None, so
# agrienergy takes no action.
PARCEL_URN_PREFIX = "urn:ngsi-ld:AgriParcel:"
ENTITY_ID_PREFIX = "urn:ngsi-ld:CropHealthAssessment:"
CACHE_TTL_S = 60.0
ERROR_CACHE_TTL_S = 10.0
MAX_FUTURE_SKEW_S = 300
ACTIONABLE_FIDELITY = "iot_sensor"

_monotonic = time.monotonic
_cache: dict[tuple[str, str], tuple[float, float, "CropHealthState | None"]] = {}


@dataclass(frozen=True)
class CropHealthState:
    stress_index: float | None
    fidelity: str | None
    observed_at: datetime | None
    shade_fraction: float | None


def reset_cache() -> None:
    """Drop all cached results (test isolation)."""
    _cache.clear()


def _unwrap(raw: Any) -> Any:
    if isinstance(raw, dict):
        for k in ("value", "@value", "object"):
            if k in raw:
                return raw[k]
    return raw


def _unit_interval(raw: Any) -> float | None:
    raw = _unwrap(raw)
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    val = float(raw)
    if math.isnan(val) or not 0.0 <= val <= 1.0:
        return None
    return val


def _parse_datetime(raw: Any) -> datetime | None:
    raw = _unwrap(raw)
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
    fidelity = _unwrap(entity.get("waterStressFidelity"))
    return CropHealthState(
        stress_index=_unit_interval(entity.get("waterStressIndex")),
        fidelity=fidelity if isinstance(fidelity, str) and fidelity else None,
        observed_at=_parse_datetime(entity.get("waterStressObservedAt")),
        shade_fraction=_unit_interval(entity.get("shadeFraction")),
    )


def _belongs_to(entity: dict, parcel_urn: str) -> bool:
    return any(
        _unwrap(entity.get(attr)) == parcel_urn
        for attr in ("hasAgriParcel", "refAgriParcel")
    )


def _pick_freshest(entities: list[dict], parcel_urn: str) -> CropHealthState | None:
    """Max ``waterStressObservedAt``; entities without it rank last.

    The newest id is not necessarily the freshest observation (day rollover).
    Entities not linked to ``parcel_urn`` are ignored.
    """
    best: CropHealthState | None = None
    for entity in entities:
        if not isinstance(entity, dict) or not _belongs_to(entity, parcel_urn):
            continue
        state = _to_state(entity)
        if best is None:
            best = state
        elif state.observed_at is not None and (
            best.observed_at is None or state.observed_at > best.observed_at
        ):
            best = state
    return best


def _is_not_found(exc: Exception) -> bool:
    return (
        isinstance(exc, httpx.HTTPStatusError)
        and exc.response is not None
        and exc.response.status_code == 404
    )


async def fetch_crop_health_state(
    orion,
    tenant_id: str,
    parcel_urn: str | None,
    *,
    now: datetime | None = None,
) -> CropHealthState | None:
    if not parcel_urn or not parcel_urn.startswith(PARCEL_URN_PREFIX):
        return None
    parcel_id = parcel_urn[len(PARCEL_URN_PREFIX):]
    if not parcel_id:
        return None
    key = (tenant_id, parcel_urn)
    mono = _monotonic()
    hit = _cache.get(key)
    if hit is not None and mono - hit[0] < hit[1]:
        return hit[2]
    now_utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    days = (now_utc, now_utc - timedelta(days=1))
    entities: list[dict] = []
    try:
        for day in days:
            entity_id = f"{ENTITY_ID_PREFIX}{parcel_id}-{day:%Y%m%d}"
            try:
                entities.append(await orion.get_entity(entity_id, options="keyValues"))
            except Exception as exc:
                if not _is_not_found(exc):
                    raise
    except Exception as exc:  # fail-safe: no state means no action
        logger.warning(
            "crop-health state read failed tenant=%s parcel=%s error=%s",
            tenant_id, parcel_urn, exc,
        )
        _cache[key] = (mono, ERROR_CACHE_TTL_S, None)
        return None
    state = _pick_freshest(entities, parcel_urn)
    _cache[key] = (mono, CACHE_TTL_S, state)
    return state


def gate_biology(
    state: CropHealthState | None, *, max_age_s: int, now: datetime
) -> tuple[dict[str, float], str]:
    """Biology scalars plus the reason: ``ok``, ``no_state``, ``not_iot_sensor``, ``stale``."""
    if state is None:
        return {}, "no_state"
    if state.fidelity != ACTIONABLE_FIDELITY:
        return {}, "not_iot_sensor"
    if state.stress_index is None or state.observed_at is None:
        return {}, "no_state"
    age_s = (now - state.observed_at).total_seconds()
    if age_s < -MAX_FUTURE_SKEW_S:
        return {}, "stale"
    age_s = max(age_s, 0.0)
    if age_s > max_age_s:
        return {}, "stale"
    return {"stress_index": state.stress_index}, "ok"


def biology_from_state(
    state: CropHealthState | None, *, max_age_s: int, now: datetime
) -> dict[str, float]:
    """``{"stress_index": x}`` only for a fresh ``iot_sensor`` index, else ``{}``."""
    return gate_biology(state, max_age_s=max_age_s, now=now)[0]
