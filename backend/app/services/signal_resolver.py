"""Resolve signalMapping entries from Orion-LD entities into algorithm context."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import httpx

from app.services.orion import get_entity_or_none

logger = logging.getLogger(__name__)

# Conservative storm-stow tilt when a required sensor is unavailable (physical safety).
REQUIRED_SIGNAL_STOW_TILT = 0.0


@dataclass
class SignalResolution:
    values: dict[str, float] = field(default_factory=dict)
    missing_required: list[str] = field(default_factory=list)


def _get_float_attr(entity: dict, key: str, default: float = 0.0) -> float:
    attr = entity.get(key)
    if attr is None:
        return default
    if isinstance(attr, dict) and "value" in attr:
        try:
            return float(attr["value"])
        except (TypeError, ValueError):
            return default
    try:
        return float(attr)
    except (TypeError, ValueError):
        return default


def parse_signal_mapping(tracker: dict) -> list[dict]:
    """Return list of mapping dicts from tracker signalMapping NGSI-LD Property."""
    mapping = tracker.get("signalMapping", {}).get("value") or tracker.get("signalMapping")
    if not isinstance(mapping, list):
        return []
    out: list[dict] = []
    for item in mapping:
        if not isinstance(item, dict):
            continue
        ctx_key = item.get("contextKey")
        entity_id = item.get("entityId")
        attr_name = item.get("attribute", "value")
        if ctx_key and entity_id:
            out.append({
                "contextKey": ctx_key,
                "entityId": entity_id,
                "attribute": attr_name,
                "required": bool(item.get("required")),
            })
    return out


async def resolve_signal_mapping(orion, mapping: list[dict]) -> SignalResolution:
    """Fetch mapped entities via OrionClient.

    Optional signals: per-item errors are silenced (algorithm uses var defaults).
    Required signals: missing entity/attribute/HTTP error → missing_required list.
    """
    values: dict[str, float] = {}
    missing_required: list[str] = []
    for item in mapping:
        ctx_key = item["contextKey"]
        entity_id = item["entityId"]
        attr_name = item["attribute"]
        required = bool(item.get("required"))
        try:
            entity = await get_entity_or_none(orion, entity_id)
            if entity is None:
                if required:
                    missing_required.append(ctx_key)
                    logger.warning(
                        "Required signal %s: entity %s not found", ctx_key, entity_id)
                else:
                    logger.debug("Optional signal %s: entity %s not found", ctx_key, entity_id)
                continue
            if entity.get(attr_name) is None:
                if required:
                    missing_required.append(ctx_key)
                    logger.warning(
                        "Required signal %s: attribute %s missing on %s",
                        ctx_key, attr_name, entity_id,
                    )
                continue
            values[ctx_key] = _get_float_attr(entity, attr_name, 0.0)
        except httpx.HTTPError as exc:
            if required:
                missing_required.append(ctx_key)
                logger.warning(
                    "Required signal %s from %s failed: %s", ctx_key, entity_id, exc)
            else:
                logger.debug("Optional signal %s from %s failed: %s", ctx_key, entity_id, exc)
    return SignalResolution(values=values, missing_required=missing_required)


def context_from_flat_sensors(flat: dict[str, float]) -> dict:
    """Build nested context for AlgorithmEngine from flat keys like 'weather.ghi'."""
    context: dict = {}
    for key, value in flat.items():
        parts = key.split(".", 1)
        if len(parts) == 1:
            context[key] = value
        else:
            group, sub = parts[0], parts[1]
            if group not in context:
                context[group] = {}
            context[group][sub] = value
    return context


def forced_stow_orientation(current_azimuth: float) -> tuple[float, float]:
    """Return (tilt, azimuth) for required-signal fault — flat panel, keep heading."""
    return (REQUIRED_SIGNAL_STOW_TILT, current_azimuth)
