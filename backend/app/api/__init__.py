"""
AgriEnergy Orchestrator Backend - API Routes
"""

from datetime import datetime
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.middleware import TokenPayload, get_tenant_id, require_roles
from app.models import (
    AlgorithmUpdate,
    CreateParkRequest,
    OrientationStatus,
    ParcelItem,
    ParcelsResponse,
    ParkSummary,
    ParksResponse,
    ParkTrackerItem,
    PowerStatus,
    SignalMappingItem,
    SignalMappingUpdate,
    SignalSource,
    SignalSourceAttribute,
    SignalSourcesResponse,
    SimulationRequest,
    SimulationResponse,
    TrackerStatusResponse,
)
from app.engines.pv_engine import PVEngine, PVSpec
from app.engines.shadow_engine import ShadowEngine
from app.models.ngsi import NGSILDSubscriptionPayload
from app.services.ngsi_client import ContextBrokerClient
from app.services.intelligence_client import IntelligenceClient
from app.services.device_command_client import DeviceCommandClient
from app.engines.algorithm_engine import AlgorithmEngine

logger = logging.getLogger(__name__)

router = APIRouter(tags=["AgriEnergy Orchestrator"])


def _get_float_attr(entity: dict, key: str, default: float = 0.0) -> float:
    """Extract float from NGSI-LD entity attribute (Property with value)."""
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


def _parse_signal_mapping(tracker: dict) -> list[dict]:
    """Return list of {contextKey, entityId, attribute} from tracker signalMapping."""
    mapping = tracker.get("signalMapping", {}).get("value") or tracker.get("signalMapping")
    if not isinstance(mapping, list):
        return []
    out = []
    for item in mapping:
        if not isinstance(item, dict):
            continue
        ctx_key = item.get("contextKey")
        entity_id = item.get("entityId")
        attr_name = item.get("attribute", "value")
        if ctx_key and entity_id:
            out.append({"contextKey": ctx_key, "entityId": entity_id, "attribute": attr_name})
    return out


async def _resolve_signal_mapping(
    ngsi: ContextBrokerClient,
    tenant_id: str,
    mapping: list[dict],
) -> dict[str, float]:
    """Fetch each mapped entity from Orion and extract attribute value. Returns contextKey -> float."""
    result: dict[str, float] = {}
    for item in mapping:
        ctx_key = item["contextKey"]
        entity_id = item["entityId"]
        attr_name = item["attribute"]
        try:
            entity = await ngsi.get_entity(tenant_id, entity_id)
            if entity is None:
                continue
            val = _get_float_attr(entity, attr_name, 0.0)
            result[ctx_key] = val
        except Exception as e:
            logger.debug("Resolve signal %s from %s: %s", ctx_key, entity_id, e)
    return result


def _context_from_flat_sensors(flat: dict[str, float]) -> dict:
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


def _build_telemetry_for_intelligence(context: dict) -> dict:
    """
    Build telemetry dict for Intelligence evaluate_status from nested context.
    Maps sensors.* / weather.* to keys expected by Intelligence (soil_moisture, leaf_temperature, dendrometer_value, par_under_panel).
    """
    telemetry: dict = {}
    sensors = context.get("sensors") or {}
    weather = context.get("weather") or {}
    for key, val in [("soil_moisture", sensors.get("soil_moisture") or weather.get("soil_moisture")),
                     ("leaf_temperature", sensors.get("leaf_temperature")),
                     ("dendrometer_value", sensors.get("dendrometer_value") or sensors.get("dendrometer_shrinkage")),
                     ("par_under_panel", sensors.get("par_under_panel"))]:
        if val is not None and isinstance(val, (int, float)):
            telemetry[key] = float(val)
    return telemetry


def _numeric_attributes_from_entity(entity: dict) -> list[tuple[str, float | None]]:
    """Return list of (attribute_name, last_value) for attributes with numeric value."""
    skip = {"id", "type", "@context", "location"}
    out: list[tuple[str, float | None]] = []
    for key, prop in entity.items():
        if key in skip or not isinstance(prop, dict):
            continue
        val = prop.get("value")
        if val is None:
            continue
        try:
            out.append((key, float(val)))
        except (TypeError, ValueError):
            continue
    return out


def _entity_name(entity: dict) -> str:
    """Extract display name from NGSI-LD entity."""
    name = entity.get("name")
    if isinstance(name, dict) and "value" in name:
        return str(name["value"])
    if isinstance(name, str):
        return name
    return entity.get("id", "—")[-32:]  # fallback: last part of id


# =============================================================================
# Instant values (panel + Cesium)
# =============================================================================


@router.get("/status", response_model=TrackerStatusResponse)
async def get_tracker_status(
    tracker_id: str = Query(..., description="AgriEnergyTracker entity ID"),
    tenant_id: str = Depends(get_tenant_id),
):
    """
    Return instant values for a tracker: orientation, power, storage, mapped sensors.
    Used by the frontend panel and to drive Cesium GLB orientation.
    """
    ngsi = ContextBrokerClient()
    tracker = await ngsi.get_entity(tenant_id, tracker_id)
    if not tracker:
        raise HTTPException(status_code=404, detail="Tracker not found")

    tilt = _get_float_attr(tracker, "tilt", 0.0)
    azimuth = _get_float_attr(tracker, "azimuth", 180.0)
    measured_w = _get_float_attr(tracker, "powerW") or _get_float_attr(tracker, "measuredPowerW")
    if measured_w == 0.0:
        measured_w = None
    expected_w = _get_float_attr(tracker, "expectedPowerW")
    if expected_w == 0.0:
        expected_w = None

    mapping_list = _parse_signal_mapping(tracker)
    sensors = await _resolve_signal_mapping(ngsi, tenant_id, mapping_list)
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
        sensors=sensors,
        signal_mapping=signal_mapping,
        active_algorithm_id=active_algorithm_id,
        timestamp=datetime.utcnow().isoformat() + "Z",
    )


# =============================================================================
# Signal sources (for UI dropdowns)
# =============================================================================

DEFAULT_SIGNAL_ENTITY_TYPES = ("WeatherObserved", "AgriSensor", "Device")


@router.get("/signal-sources", response_model=SignalSourcesResponse)
async def get_signal_sources(
    tenant_id: str = Depends(get_tenant_id),
    entity_types: str = Query(
        default=",".join(DEFAULT_SIGNAL_ENTITY_TYPES),
        description="Comma-separated NGSI-LD entity types (e.g. WeatherObserved,AgriSensor,Device)",
    ),
):
    """
    List entities that can be used as signal sources for algorithm context.
    Returns entity id, name, type, and numeric attributes (for dropdowns in Configure signals UI).
    """
    ngsi = ContextBrokerClient()
    types_list = [t.strip() for t in entity_types.split(",") if t.strip()]
    if not types_list:
        types_list = list(DEFAULT_SIGNAL_ENTITY_TYPES)
    sources: list[SignalSource] = []
    for etype in types_list:
        entities = await ngsi.get_entities_by_type(tenant_id, etype)
        for entity in entities:
            eid = entity.get("id")
            if not eid:
                continue
            attrs = _numeric_attributes_from_entity(entity)
            if not attrs:
                continue
            sources.append(
                SignalSource(
                    entity_id=eid,
                    entity_name=_entity_name(entity),
                    type=etype,
                    attributes=[SignalSourceAttribute(name=a, last_value=v) for a, v in attrs],
                )
            )
    return SignalSourcesResponse(sources=sources)


# =============================================================================
# Algorithms (built-in presets for UI selector)
# =============================================================================


@router.get("/algorithms")
async def get_algorithms():
    """
    List built-in algorithm presets (id, name, logic). For frontend algorithm selector.
    Rules use var-with-default for fail-safe (missing sensors/biology).
    """
    return {"algorithms": AlgorithmEngine.builtin_algorithms()}


# =============================================================================
# Solar parks (AgriSolarPark — Option B)
# =============================================================================

ENTITY_TYPE_AGRI_SOLAR_PARK = "AgriSolarPark"


def _ref_agri_parcel_from_entity(entity: dict) -> str | None:
    """Extract parcel URN from refAgriParcel attribute."""
    ref = entity.get("refAgriParcel") or {}
    if isinstance(ref, dict):
        return ref.get("object") or ref.get("value")
    return str(ref) if ref else None


@router.get("/parcels", response_model=ParcelsResponse)
async def get_parcels(tenant_id: str = Depends(get_tenant_id)):
    """List parcels (AgriParcel) for dropdown when creating a solar park."""
    ngsi = ContextBrokerClient()
    entities = await ngsi.get_entities_by_type(tenant_id, "AgriParcel")
    return ParcelsResponse(
        parcels=[ParcelItem(id=e.get("id", ""), name=_entity_name(e)) for e in entities if e.get("id")]
    )


@router.get("/parks", response_model=ParksResponse)
async def get_parks(
    tenant_id: str = Depends(get_tenant_id),
):
    """
    List all solar parks (AgriSolarPark entities). Each park has refAgriParcel;
    trackers are matched by refAgriParcel so we include tracker_count and tracker_ids.
    """
    ngsi = ContextBrokerClient()
    parks_raw = await ngsi.get_entities_by_type(tenant_id, ENTITY_TYPE_AGRI_SOLAR_PARK)
    trackers_all = await ngsi.get_entities_by_type(tenant_id, "AgriEnergyTracker")
    # Group trackers by parcel URN
    by_parcel: dict[str, list[dict]] = {}
    for t in trackers_all:
        parcel_urn = _ref_agri_parcel_from_entity(t)
        if parcel_urn:
            by_parcel.setdefault(parcel_urn, []).append(t)
    # Build response
    parks: list[ParkSummary] = []
    for p in parks_raw:
        park_id = p.get("id")
        if not park_id:
            continue
        name = _entity_name(p)
        parcel_urn = _ref_agri_parcel_from_entity(p)
        if not parcel_urn:
            parks.append(
                ParkSummary(
                    park_id=park_id,
                    name=name,
                    ref_agri_parcel="",
                    tracker_count=0,
                    tracker_ids=[],
                )
            )
            continue
        trackers_in_parcel = by_parcel.get(parcel_urn, [])
        parcel_name: str | None = None
        try:
            parcel_entity = await ngsi.get_entity(tenant_id, parcel_urn)
            if parcel_entity:
                parcel_name = _entity_name(parcel_entity)
        except Exception:
            pass
        parks.append(
            ParkSummary(
                park_id=park_id,
                name=name,
                ref_agri_parcel=parcel_urn,
                parcel_name=parcel_name,
                tracker_count=len(trackers_in_parcel),
                tracker_ids=[t.get("id") for t in trackers_in_parcel if t.get("id")],
            )
        )
    return ParksResponse(parks=parks)


@router.get("/parks/{park_id}/trackers")
async def get_park_trackers(
    park_id: str,
    tenant_id: str = Depends(get_tenant_id),
):
    """List trackers that belong to this park (same refAgriParcel as the park)."""
    ngsi = ContextBrokerClient()
    park = await ngsi.get_entity(tenant_id, park_id)
    if not park or park.get("type") != ENTITY_TYPE_AGRI_SOLAR_PARK:
        raise HTTPException(status_code=404, detail="Park not found")
    parcel_urn = _ref_agri_parcel_from_entity(park)
    if not parcel_urn:
        return {"trackers": []}
    trackers_all = await ngsi.get_entities_by_type(tenant_id, "AgriEnergyTracker")
    out: list[ParkTrackerItem] = []
    for t in trackers_all:
        if _ref_agri_parcel_from_entity(t) != parcel_urn:
            continue
        out.append(ParkTrackerItem(tracker_id=t.get("id", ""), name=_entity_name(t)))
    return {"trackers": out}


@router.post("/parks", status_code=status.HTTP_201_CREATED)
async def create_park(
    body: CreateParkRequest,
    tenant_id: str = Depends(get_tenant_id),
):
    """
    Create a new solar park (AgriSolarPark entity) linked to a parcel.
    Requires context_broker_url to be set in config (Orion-LD).
    """
    ngsi = ContextBrokerClient()
    entity_id = f"urn:ngsi-ld:{ENTITY_TYPE_AGRI_SOLAR_PARK}:{uuid.uuid4().hex}"
    entity = {
        "id": entity_id,
        "type": ENTITY_TYPE_AGRI_SOLAR_PARK,
        "name": {"type": "Property", "value": body.name},
        "refAgriParcel": {"type": "Relationship", "object": body.ref_agri_parcel},
    }
    ok = await ngsi.create_entity(tenant_id, entity)
    if not ok:
        raise HTTPException(
            status_code=502,
            detail="Failed to create park in Context Broker (check context_broker_url)",
        )
    return {"park_id": entity_id, "name": body.name, "ref_agri_parcel": body.ref_agri_parcel}


@router.patch("/trackers/{tracker_id}/algorithm")
async def update_tracker_algorithm(
    tracker_id: str,
    body: AlgorithmUpdate,
    tenant_id: str = Depends(get_tenant_id),
):
    """
    Set the activeAlgorithm of an AgriEnergyTracker. If body.activeAlgorithm has only "id"
    (e.g. {"id": "default:maximize"}), resolve from built-in presets and store the logic;
    otherwise store the given object in Orion.
    """
    ngsi = ContextBrokerClient()
    algo = body.activeAlgorithm
    if set(algo.keys()) <= {"id"} and algo.get("id"):
        preset_id = algo["id"]
        presets = {p["id"]: p["logic"] for p in AlgorithmEngine.builtin_algorithms()}
        if preset_id not in presets:
            raise HTTPException(status_code=400, detail=f"Unknown algorithm id: {preset_id}")
        logic = presets[preset_id]
    else:
        logic = algo
    ok = await ngsi.update_entity_attribute(tenant_id, tracker_id, "activeAlgorithm", logic)
    if not ok:
        raise HTTPException(status_code=502, detail="Failed to update tracker in Context Broker")
    return {"status": "updated", "tracker_id": tracker_id, "activeAlgorithm": logic}


@router.patch("/trackers/{tracker_id}/signal-mapping")
async def update_tracker_signal_mapping(
    tracker_id: str,
    body: SignalMappingUpdate,
    tenant_id: str = Depends(get_tenant_id),
):
    """
    Update the signalMapping attribute of an AgriEnergyTracker in Orion-LD.
    Called by the frontend when the user saves "Configure signals".
    """
    ngsi = ContextBrokerClient()
    payload = [item.model_dump() for item in body.signalMapping]
    ok = await ngsi.update_entity_attribute(tenant_id, tracker_id, "signalMapping", payload)
    if not ok:
        raise HTTPException(status_code=502, detail="Failed to update tracker in Context Broker")
    return {"status": "updated", "tracker_id": tracker_id, "signalMapping": payload}


# =============================================================================
# Simulation (Sandbox / API)
# =============================================================================

@router.post("/simulate", response_model=SimulationResponse)
async def simulate(request: SimulationRequest):
    """
    Run a one-shot PV + shadow simulation for a tracker/parcel and target tilt.
    Used by the frontend Sandbox and by external callers.
    """
    tracker = request.tracker
    parcel = request.parcel
    telemetry = request.telemetry
    target_tilt = request.target_tilt

    try:
        sim_time = datetime.fromisoformat(telemetry.timestamp.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        sim_time = datetime.utcnow()

    pv_engine = PVEngine(tracker.lat, tracker.lon)
    spec = PVSpec(
        tilt=target_tilt,
        azimuth=telemetry.actual_azimuth,
        capacity_w=tracker.capacity_w,
        module_area_m2=tracker.panel_width * tracker.panel_length,
    )
    pv_res = pv_engine.calculate_expected_power(
        sim_time,
        spec,
        telemetry.ghi,
        telemetry.dni,
        telemetry.dhi,
    )
    shadow_engine = ShadowEngine()
    shadow_res = shadow_engine.calculate_shadow_polygon(
        panel_width=tracker.panel_width,
        panel_length=tracker.panel_length,
        panel_tilt=target_tilt,
        panel_azimuth=telemetry.actual_azimuth,
        solar_elevation=pv_res["solar_elevation"],
        solar_azimuth=pv_res["solar_azimuth"],
        terrain_slope=parcel.slope,
        terrain_aspect=parcel.aspect,
    )
    polygon_list = list(shadow_res["polygon"]) if shadow_res["polygon"] else []
    return SimulationResponse(
        expected_power_w=round(pv_res["expected_power_w"], 2),
        shadow_area_m2=round(shadow_res["area_m2"], 4),
        shadow_polygon_2d=polygon_list,
    )


# =============================================================================
# NGSI-LD Notification Webhook
# =============================================================================

@router.post("/notify", status_code=status.HTTP_200_OK)
async def process_ngsild_notification(
    payload: NGSILDSubscriptionPayload,
    tenant_id: str = Depends(get_tenant_id)
):
    """
    Webhook para recibir notificaciones (suscripciones) de Orion-LD.
    Se dispara cuando cambian entidades observadas como WeatherObserved o AgriEnergyTracker.
    """
    logger.info(f"Received NGSI-LD notification for subscription {payload.subscriptionId}")
    
    ngsi_client = ContextBrokerClient()
    intelligence_client = IntelligenceClient()
    shadow_engine = ShadowEngine()
    
    for entity in payload.data:
        entity_id = entity.get("id")
        entity_type = entity.get("type", "")
        
        logger.info(f"Processing entity {entity_id} of type {entity_type}")
        
        # 1. Extraer clima del evento si es WeatherObserved (idealmente usaríamos el evento para extraer valores)
        ghi = 800.0  # Placeholder si el evento no lo trae directamente
        dni = 600.0
        dhi = 200.0
        if entity_type == "WeatherObserved":
            if "illuminance" in entity:
                ghi = float(entity["illuminance"].get("value", ghi))
            elif "solarRadiation" in entity:
                 ghi = float(entity["solarRadiation"].get("value", ghi))
                 
            # Buscamos los trackers afectados y recalculamos (Lazo cerrado Reactivo)
            trackers = await ngsi_client.get_entities_by_type(tenant_id, "AgriEnergyTracker")
        elif entity_type == "AgriEnergyTracker":
            trackers = [entity] # El propio entity es el tracker
        else:
            continue
            
        # 2. Bucle de Evaluación
        for tracker in trackers:
            tracker_id = tracker.get("id")
            parcel_id = tracker.get("refAgriParcel", {}).get("object", "urn:ngsi-ld:AgriParcel:Default")
            
            # Panel parameters — SDM-aligned names with legacy fallback
            _dim = tracker.get("panelDimension", {}).get("value", {})
            p_width = float(_dim.get("width", 0) or tracker.get("width", {}).get("value", 2.0))
            p_length = float(_dim.get("length", 0) or tracker.get("length", {}).get("value", 4.0))
            p_cap = float(tracker.get("NominalPower", {}).get("value", 0) or tracker.get("capacityW", {}).get("value", 500.0))
            p_tilt = float(tracker.get("tilt", {}).get("value", 0.0))
            p_azimuth = float(tracker.get("azimuth", {}).get("value", 180.0))
            lat = float(tracker.get("location", {}).get("value", {}).get("coordinates", [43.0, -2.0])[1])
            lon = float(tracker.get("location", {}).get("value", {}).get("coordinates", [43.0, -2.0])[0])

            # 3. Build context for algorithm: signalMapping -> weather, tracker, sensors
            context = {"weather": {"ghi": ghi, "dni": dni}, "tracker": {"tilt": p_tilt, "azimuth": p_azimuth}}
            mapping_list = _parse_signal_mapping(tracker)
            if mapping_list:
                resolved = await _resolve_signal_mapping(ngsi_client, tenant_id, mapping_list)
                if resolved:
                    nested = _context_from_flat_sensors(resolved)
                    for group, data in nested.items():
                        if isinstance(data, dict):
                            context.setdefault(group, {}).update(data)
                        else:
                            context[group] = data
                    ghi = context.get("weather", {}).get("ghi", ghi)
                    dni = context.get("weather", {}).get("dni", dni)
                    dhi = context.get("weather", {}).get("dhi", dhi)

            # 4. Current shadow (for Intelligence) and PV solar position
            pv_engine = PVEngine(lat, lon)
            sim_time = datetime.utcnow()
            pv_current = pv_engine.calculate_expected_power(
                sim_time,
                PVSpec(tilt=p_tilt, azimuth=p_azimuth, capacity_w=p_cap, module_area_m2=p_width * p_length),
                ghi, dni, dhi,
            )
            shadow_current = shadow_engine.calculate_shadow_polygon(
                panel_width=p_width, panel_length=p_length,
                panel_tilt=p_tilt, panel_azimuth=p_azimuth,
                solar_elevation=pv_current["solar_elevation"],
                solar_azimuth=pv_current["solar_azimuth"],
            )
            shadow_polygon_2d = list(shadow_current["polygon"]) if shadow_current.get("polygon") else []

            # 5. Call Intelligence evaluate_status; inject biology (fail-safe: empty or stress_index 0)
            telemetry = _build_telemetry_for_intelligence(context)
            biology = await intelligence_client.evaluate_status(
                tenant_id=tenant_id,
                tracker_id=tracker_id,
                parcel_id=parcel_id,
                timestamp=datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                shadow_polygon_2d=shadow_polygon_2d,
                telemetry=telemetry,
            )
            # Fail-safe: inject only empty dict; defaults belong in JSON Logic (var fallback).
            context["biology"] = biology if biology else {}

            # 6. Evaluate algorithm and resolve orientation
            active_algo = tracker.get("activeAlgorithm", {}).get("value", AlgorithmEngine.default_algorithm())
            algo_result = AlgorithmEngine.evaluate_rule(active_algo, context)
            _rota = tracker.get("rotationAxis")
            rotation_axis = (_rota.get("value") if isinstance(_rota, dict) else _rota) if _rota else None
            if rotation_axis is not None and not isinstance(rotation_axis, str):
                rotation_axis = None
            new_target_tilt, new_target_azimuth = AlgorithmEngine.resolve_orientation(
                algo_result, p_tilt, p_azimuth, rotation_axis
            )

            # 7. Digital twin: PV + shadow for the *new* orientation (logging and consistency)
            spec = PVSpec(tilt=new_target_tilt, azimuth=new_target_azimuth, capacity_w=p_cap, module_area_m2=p_width * p_length)
            pv_res = pv_engine.calculate_expected_power(sim_time, spec, ghi, dni, dhi)
            shadow_res = shadow_engine.calculate_shadow_polygon(
                panel_width=p_width, panel_length=p_length,
                panel_tilt=new_target_tilt, panel_azimuth=new_target_azimuth,
                solar_elevation=pv_res["solar_elevation"],
                solar_azimuth=pv_res["solar_azimuth"],
            )
            stress_index = (context.get("biology") or {}).get("stress_index") or 0.0

            logger.info(
                "Tracker %s: target tilt=%.1f azimuth=%.1f -> shadow=%.2fm2 stress=%.2f",
                tracker_id, new_target_tilt, new_target_azimuth, shadow_res["area_m2"], stress_index
            )

            # 8. Update Context Broker: targetTilt, targetAzimuth, tilt, azimuth, modelRotation
            await ngsi_client.update_entity_attribute(tenant_id, tracker_id, "targetTilt", new_target_tilt)
            await ngsi_client.update_entity_attribute(tenant_id, tracker_id, "targetAzimuth", new_target_azimuth)
            await ngsi_client.update_entity_attribute(tenant_id, tracker_id, "tilt", new_target_tilt)
            await ngsi_client.update_entity_attribute(tenant_id, tracker_id, "azimuth", new_target_azimuth)
            # Cesium headingPitchRoll: heading=azimuth, pitch=-tilt (deg), roll=0
            model_rotation = [new_target_azimuth, -new_target_tilt, 0.0]
            await ngsi_client.update_entity_attribute(tenant_id, tracker_id, "modelRotation", model_rotation)

            # 7. Send MQTT command to physical device if refDevice is set
            ref_device = tracker.get("refDevice", {}).get("value") or tracker.get("refDevice")
            if isinstance(ref_device, str) and ref_device.strip():
                device_client = DeviceCommandClient()
                await device_client.send_tracker_command(
                    tenant_id, ref_device.strip(), new_target_tilt, new_target_azimuth
                )

    return {"status": "processed", "entities": len(payload.data)}


# =============================================================================
# Admin Routes (Role-Protected)
# =============================================================================

@router.get("/admin/stats")
async def get_stats(
    user: TokenPayload = Depends(require_roles("TenantAdmin", "PlatformAdmin")),
):
    """
    Get module statistics. Requires TenantAdmin or PlatformAdmin role.
    Metrics can be extended later (e.g. notification counts, active trackers).
    """
    return {
        "total_tenants": 0,
        "total_items": 0,
        "user": user.email,
    }
