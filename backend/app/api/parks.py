"""Solar parks, parcels, and tracker configuration routes."""

import logging
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import orion_dep
from app.engines.algorithm_engine import AlgorithmEngine
from app.models import (
    AlgorithmUpdate,
    CreateParkRequest,
    ParcelItem,
    ParcelsResponse,
    ParkSummary,
    ParksResponse,
    ParkTrackerItem,
    SignalMappingUpdate,
)
from app.services.ngsi_helpers import entity_name, ref_agri_parcel_from_entity
from app.services.orion import get_entity_or_none, prop, rel
from app.services.subscriptions import ensure_subscriptions

logger = logging.getLogger(__name__)

router = APIRouter(tags=["AgriEnergy Orchestrator"])

ENTITY_TYPE_AGRI_SOLAR_PARK = "AgriSolarPark"


@router.get("/parcels", response_model=ParcelsResponse)
async def get_parcels(orion=Depends(orion_dep)):
    """List parcels (AgriParcel) for dropdown when creating a solar park."""
    try:
        entities = await orion.query_entities(type="AgriParcel", limit=500)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Context Broker unavailable") from exc
    return ParcelsResponse(
        parcels=[ParcelItem(id=e.get("id", ""), name=entity_name(e)) for e in entities if e.get("id")]
    )


@router.get("/parks", response_model=ParksResponse)
async def get_parks(orion=Depends(orion_dep)):
    """List solar parks (AgriSolarPark) with tracker counts per parcel."""
    await ensure_subscriptions(orion.tenant_id)
    try:
        parks_raw = await orion.query_entities(type=ENTITY_TYPE_AGRI_SOLAR_PARK, limit=500)
        trackers_all = await orion.query_entities(type="AgriEnergyTracker", limit=500)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Context Broker unavailable") from exc
    by_parcel: dict[str, list[dict]] = {}
    for t in trackers_all:
        parcel_urn = ref_agri_parcel_from_entity(t)
        if parcel_urn:
            by_parcel.setdefault(parcel_urn, []).append(t)
    parks: list[ParkSummary] = []
    for p in parks_raw:
        park_id = p.get("id")
        if not park_id:
            continue
        name = entity_name(p)
        parcel_urn = ref_agri_parcel_from_entity(p)
        if not parcel_urn:
            parks.append(ParkSummary(
                park_id=park_id, name=name, ref_agri_parcel="",
                tracker_count=0, tracker_ids=[],
            ))
            continue
        trackers_in_parcel = by_parcel.get(parcel_urn, [])
        parcel_name: str | None = None
        try:
            parcel_entity = await get_entity_or_none(orion, parcel_urn)
            if parcel_entity:
                parcel_name = entity_name(parcel_entity)
        except httpx.HTTPError:
            logger.debug("Parcel name lookup failed for %s", parcel_urn)
        parks.append(ParkSummary(
            park_id=park_id,
            name=name,
            ref_agri_parcel=parcel_urn,
            parcel_name=parcel_name,
            tracker_count=len(trackers_in_parcel),
            tracker_ids=[t.get("id") for t in trackers_in_parcel if t.get("id")],
        ))
    return ParksResponse(parks=parks)


@router.get("/parks/{park_id}/trackers")
async def get_park_trackers(park_id: str, orion=Depends(orion_dep)):
    """Trackers belonging to this park (same hasAgriParcel)."""
    try:
        park = await get_entity_or_none(orion, park_id)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Context Broker unavailable") from exc
    if not park or park.get("type") != ENTITY_TYPE_AGRI_SOLAR_PARK:
        raise HTTPException(status_code=404, detail="Park not found")
    parcel_urn = ref_agri_parcel_from_entity(park)
    if not parcel_urn:
        return {"trackers": []}
    try:
        trackers_all = await orion.query_entities(type="AgriEnergyTracker", limit=500)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Context Broker unavailable") from exc
    out: list[ParkTrackerItem] = []
    for t in trackers_all:
        if ref_agri_parcel_from_entity(t) != parcel_urn:
            continue
        out.append(ParkTrackerItem(tracker_id=t.get("id", ""), name=entity_name(t)))
    return {"trackers": out}


@router.post("/parks", status_code=status.HTTP_201_CREATED)
async def create_park(body: CreateParkRequest, orion=Depends(orion_dep)):
    """Create AgriSolarPark entity linked to a parcel."""
    await ensure_subscriptions(orion.tenant_id)
    entity_id = f"urn:ngsi-ld:{ENTITY_TYPE_AGRI_SOLAR_PARK}:{uuid.uuid4().hex}"
    entity = {
        "id": entity_id,
        "type": ENTITY_TYPE_AGRI_SOLAR_PARK,
        "name": prop(body.name),
        "hasAgriParcel": rel(body.ref_agri_parcel),
    }
    try:
        await orion.create_entity(entity)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Failed to create park in Context Broker") from exc
    return {"park_id": entity_id, "name": body.name, "ref_agri_parcel": body.ref_agri_parcel}


@router.patch("/trackers/{tracker_id}/algorithm")
async def update_tracker_algorithm(
    tracker_id: str,
    body: AlgorithmUpdate,
    orion=Depends(orion_dep),
):
    """Set activeAlgorithm on AgriEnergyTracker (JSON Logic or preset id)."""
    algo = body.activeAlgorithm
    if set(algo.keys()) <= {"id"} and algo.get("id"):
        preset_id = algo["id"]
        presets = {p["id"]: p["logic"] for p in AlgorithmEngine.builtin_algorithms()}
        if preset_id not in presets:
            raise HTTPException(status_code=400, detail=f"Unknown algorithm id: {preset_id}")
        logic = presets[preset_id]
    else:
        logic = algo
    try:
        await orion.append_entity_attrs(tracker_id, {"activeAlgorithm": prop(logic)})
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Failed to update tracker in Context Broker") from exc
    return {"status": "updated", "tracker_id": tracker_id, "activeAlgorithm": logic}


@router.patch("/trackers/{tracker_id}/signal-mapping")
async def update_tracker_signal_mapping(
    tracker_id: str,
    body: SignalMappingUpdate,
    orion=Depends(orion_dep),
):
    """Update signalMapping on AgriEnergyTracker in Orion-LD."""
    payload = [item.model_dump() for item in body.signalMapping]
    try:
        await orion.append_entity_attrs(tracker_id, {"signalMapping": prop(payload)})
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Failed to update tracker in Context Broker") from exc
    return {"status": "updated", "tracker_id": tracker_id, "signalMapping": payload}
