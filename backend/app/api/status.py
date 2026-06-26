"""Tracker status, signal sources, and algorithm presets."""

from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import orion_dep
from app.engines.algorithm_engine import AlgorithmEngine
from app.models import (
    OrientationStatus,
    PowerStatus,
    SignalMappingItem,
    SignalSource,
    SignalSourceAttribute,
    SignalSourcesResponse,
    TrackerStatusResponse,
)
from app.services.ngsi_helpers import (
    entity_name,
    get_control_status_from_tracker,
    get_float_attr,
    numeric_attributes_from_entity,
)
from app.services.orion import get_entity_or_none
from app.services.signal_resolver import parse_signal_mapping, resolve_signal_mapping

router = APIRouter(tags=["AgriEnergy Orchestrator"])

DEFAULT_SIGNAL_ENTITY_TYPES = ("WeatherObserved", "AgriSensor")


@router.get("/status", response_model=TrackerStatusResponse)
async def get_tracker_status(
    tracker_id: str = Query(..., description="AgriEnergyTracker entity ID"),
    orion=Depends(orion_dep),
):
    """Instant values for a tracker: orientation, power, mapped sensors."""
    try:
        tracker = await get_entity_or_none(orion, tracker_id)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Context Broker unavailable") from exc
    if tracker is None:
        raise HTTPException(status_code=404, detail="Tracker not found")

    tilt = get_float_attr(tracker, "tilt", 0.0)
    azimuth = get_float_attr(tracker, "azimuth", 180.0)
    measured_w = get_float_attr(tracker, "powerW") or get_float_attr(tracker, "measuredPowerW")
    if measured_w == 0.0:
        measured_w = None
    expected_w = get_float_attr(tracker, "expectedPowerW")
    if expected_w == 0.0:
        expected_w = None

    mapping_list = parse_signal_mapping(tracker)
    resolution = await resolve_signal_mapping(orion, mapping_list)
    control_status = "degraded" if resolution.missing_required else get_control_status_from_tracker(tracker)
    signal_mapping = [SignalMappingItem(**m) for m in mapping_list] if mapping_list else None

    active_algorithm_id = None
    algo_attr = tracker.get("activeAlgorithm", {}).get("value")
    if isinstance(algo_attr, dict) and set(algo_attr.keys()) <= {"id"} and algo_attr.get("id"):
        active_algorithm_id = algo_attr["id"]

    return TrackerStatusResponse(
        tracker_id=tracker_id,
        orientation=OrientationStatus(tilt=tilt, azimuth=azimuth),
        power=PowerStatus(measured_w=measured_w, expected_w=expected_w or None),
        storage=None,
        sensors=resolution.values,
        signal_mapping=signal_mapping,
        active_algorithm_id=active_algorithm_id,
        control_status=control_status,
        signal_faults=resolution.missing_required,
        timestamp=datetime.utcnow().isoformat() + "Z",
    )


@router.get("/signal-sources", response_model=SignalSourcesResponse)
async def get_signal_sources(
    orion=Depends(orion_dep),
    entity_types: str = Query(
        default=",".join(DEFAULT_SIGNAL_ENTITY_TYPES),
        description="Comma-separated NGSI-LD entity types (e.g. WeatherObserved,AgriSensor)",
    ),
):
    """Entities usable as signal sources for algorithm context (UI dropdowns)."""
    types_list = [t.strip() for t in entity_types.split(",") if t.strip()]
    if not types_list:
        types_list = list(DEFAULT_SIGNAL_ENTITY_TYPES)
    sources: list[SignalSource] = []
    try:
        entities_by_type: list[tuple[str, list[dict]]] = [
            (etype, await orion.query_entities(type=etype, limit=500))
            for etype in types_list
        ]
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Context Broker unavailable") from exc
    for etype, entities in entities_by_type:
        for entity in entities:
            eid = entity.get("id")
            if not eid:
                continue
            attrs = numeric_attributes_from_entity(entity)
            if not attrs:
                continue
            sources.append(
                SignalSource(
                    entity_id=eid,
                    entity_name=entity_name(entity),
                    type=etype,
                    attributes=[SignalSourceAttribute(name=a, last_value=v) for a, v in attrs],
                )
            )
    return SignalSourcesResponse(sources=sources)


@router.get("/algorithms")
async def get_algorithms():
    """Built-in algorithm presets (id, name, logic) for frontend selector."""
    return {"algorithms": AlgorithmEngine.builtin_algorithms()}
