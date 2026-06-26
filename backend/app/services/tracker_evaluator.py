"""Closed-loop tracker evaluation: context -> algorithm -> Orion/MQTT actuation."""

from __future__ import annotations

import logging
from datetime import datetime

from app.engines.algorithm_engine import AlgorithmEngine
from app.engines.elevation import ElevationService
from app.engines.pv_engine import PVEngine, PVSpec
from app.services.device_command_client import DeviceCommandClient
from app.services.intelligence_client import IntelligenceClient
from app.services.ngsi_helpers import build_telemetry_for_intelligence
from app.services.orion import get_entity_or_none, prop
from app.services.signal_resolver import (
    context_from_flat_sensors,
    forced_stow_orientation,
    parse_signal_mapping,
    resolve_signal_mapping,
)

logger = logging.getLogger(__name__)

# Idempotence guard: skip writes when orientation is within tolerance.
TILT_TOLERANCE_DEG = 0.01


def angular_distance_deg(a: float, b: float) -> float:
    """Shortest angular distance in degrees (wraps at 360)."""
    return abs((a - b + 180.0) % 360.0 - 180.0)


async def evaluate_and_actuate_tracker(
    orion,
    intelligence_client,
    shadow_engine,
    tenant_id: str,
    tracker: dict,
    ghi: float,
    dni: float,
    dhi: float,
) -> None:
    """Closed-loop step for a single tracker: context -> algorithm -> actuator.

    Raises on corrupt input so the caller can isolate the failure (per-tracker
    fail-safe); a healthy tracker in the same batch must still actuate.
    """
    tracker_id = tracker.get("id")
    parcel_id = tracker.get("hasAgriParcel", {}).get("object", "urn:ngsi-ld:AgriParcel:Default")

    _dim = tracker.get("panelDimension", {}).get("value", {})
    p_width = float(
        tracker.get("panelWidth", {}).get("value")
        or _dim.get("width")
        or tracker.get("width", {}).get("value", 2.0)
    )
    p_length = float(
        tracker.get("panelLength", {}).get("value")
        or _dim.get("length")
        or tracker.get("length", {}).get("value", 4.0)
    )
    p_height = float(
        tracker.get("panelHeight", {}).get("value")
        or tracker.get("clearanceHeight", {}).get("value", 2.0)
    )
    p_cap = float(
        tracker.get("NominalPower", {}).get("value", 0)
        or tracker.get("capacityW", {}).get("value", 500.0)
    )
    p_tilt = float(tracker.get("tilt", {}).get("value", 0.0))
    p_azimuth = float(tracker.get("azimuth", {}).get("value", 180.0))
    if not p_tilt and not tracker.get("tilt"):
        _mr = tracker.get("modelRotation", {}).get("value", [0, 0, 0]) or [0, 0, 0]
        if isinstance(_mr, list) and len(_mr) >= 2:
            p_azimuth = float(_mr[0]) if float(_mr[0]) != 0 or not p_azimuth else p_azimuth
            p_tilt = -float(_mr[1])

    _loc = tracker.get("location", {}).get("value", {})
    if _loc.get("type") == "MultiPoint" and _loc.get("coordinates"):
        coords = _loc["coordinates"][0]
        lat, lon = coords[1], coords[0]
    else:
        lat = float(_loc.get("coordinates", [43.0, -2.0])[1])
        lon = float(_loc.get("coordinates", [43.0, -2.0])[0])

    parcel_slope = 0.0
    parcel_aspect = 180.0
    try:
        parcel = await get_entity_or_none(orion, parcel_id)
        if parcel:
            parcel_slope = float(parcel.get("slope", {}).get("value", 0.0))
            parcel_aspect = float(parcel.get("aspect", {}).get("value", 180.0))
    except Exception:
        pass

    context = {"weather": {"ghi": ghi, "dni": dni}, "tracker": {"tilt": p_tilt, "azimuth": p_azimuth}}
    mapping_list = parse_signal_mapping(tracker)
    signal_resolution = await resolve_signal_mapping(orion, mapping_list)
    forced_stow = bool(signal_resolution.missing_required)
    control_status = "degraded" if forced_stow else "ok"
    if signal_resolution.values:
        nested = context_from_flat_sensors(signal_resolution.values)
        for group, data in nested.items():
            if isinstance(data, dict):
                context.setdefault(group, {}).update(data)
            else:
                context[group] = data
        ghi = context.get("weather", {}).get("ghi", ghi)
        dni = context.get("weather", {}).get("dni", dni)
        dhi = context.get("weather", {}).get("dhi", dhi)
    if forced_stow:
        context["control"] = {
            "degraded": True,
            "missing_required": signal_resolution.missing_required,
        }
        logger.warning(
            "Tracker %s: required signals missing %s -> storm stow tilt=0 (tenant=%s)",
            tracker_id, signal_resolution.missing_required, tenant_id,
        )

    _loc_val = tracker.get("location", {}).get("value", {})
    is_multipoint = _loc_val.get("type") == "MultiPoint" and _loc_val.get("coordinates")
    panel_positions: list = []
    if is_multipoint:
        panel_positions = [(c[0], c[1]) for c in _loc_val["coordinates"]]
        elevation_svc = ElevationService(tenant_id=tenant_id)
        elevations = await elevation_svc.get_elevations(panel_positions, parcel_id=parcel_id)
    else:
        elevations = None

    pv_engine = PVEngine(lat, lon)
    sim_time = datetime.utcnow()
    pv_current = pv_engine.calculate_expected_power(
        sim_time,
        PVSpec(tilt=p_tilt, azimuth=p_azimuth, capacity_w=p_cap, module_area_m2=p_width * p_length),
        ghi, dni, dhi,
    )
    if is_multipoint:
        shadow_current = shadow_engine.calculate_array_shadow(
            panel_positions=panel_positions,
            panel_width=p_width, panel_length=p_length,
            panel_tilt=p_tilt, panel_azimuth=p_azimuth,
            solar_elevation=pv_current["solar_elevation"],
            solar_azimuth=pv_current["solar_azimuth"],
            clearance_height=p_height,
            terrain_slope=parcel_slope,
            terrain_aspect=parcel_aspect,
            elevations=elevations,
        )
    else:
        shadow_current = shadow_engine.calculate_shadow_polygon(
            panel_width=p_width, panel_length=p_length,
            panel_tilt=p_tilt, panel_azimuth=p_azimuth,
            solar_elevation=pv_current["solar_elevation"],
            solar_azimuth=pv_current["solar_azimuth"],
            clearance_height=p_height,
            terrain_slope=parcel_slope,
            terrain_aspect=parcel_aspect,
        )
    shadow_polygon_2d = list(shadow_current["polygon"]) if shadow_current.get("polygon") else []

    telemetry = build_telemetry_for_intelligence(context)
    biology = await intelligence_client.evaluate_status(
        tenant_id=tenant_id,
        tracker_id=tracker_id,
        parcel_id=parcel_id,
        timestamp=datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        shadow_polygon_2d=shadow_polygon_2d,
        telemetry=telemetry,
    )
    context["biology"] = biology if biology else {}

    if forced_stow:
        new_target_tilt, new_target_azimuth = forced_stow_orientation(p_azimuth)
    else:
        active_algo = tracker.get("activeAlgorithm", {}).get("value", AlgorithmEngine.default_algorithm())
        algo_result = AlgorithmEngine.evaluate_rule(active_algo, context)
        _rota = tracker.get("rotationAxis")
        rotation_axis = (_rota.get("value") if isinstance(_rota, dict) else _rota) if _rota else None
        if rotation_axis is not None and not isinstance(rotation_axis, str):
            rotation_axis = None
        new_target_tilt, new_target_azimuth = AlgorithmEngine.resolve_orientation(
            algo_result, p_tilt, p_azimuth, rotation_axis
        )

    if (
        abs(new_target_tilt - p_tilt) <= TILT_TOLERANCE_DEG
        and angular_distance_deg(new_target_azimuth, p_azimuth) <= TILT_TOLERANCE_DEG
    ):
        logger.info(
            "Tracker %s: orientation unchanged (tilt=%.2f azimuth=%.2f), skipping",
            tracker_id, p_tilt, p_azimuth,
        )
        return

    spec = PVSpec(
        tilt=new_target_tilt, azimuth=new_target_azimuth,
        capacity_w=p_cap, module_area_m2=p_width * p_length,
    )
    pv_res = pv_engine.calculate_expected_power(sim_time, spec, ghi, dni, dhi)
    if is_multipoint:
        shadow_res = shadow_engine.calculate_array_shadow(
            panel_positions=panel_positions,
            panel_width=p_width, panel_length=p_length,
            panel_tilt=new_target_tilt, panel_azimuth=new_target_azimuth,
            solar_elevation=pv_res["solar_elevation"],
            solar_azimuth=pv_res["solar_azimuth"],
            clearance_height=p_height,
            terrain_slope=parcel_slope,
            terrain_aspect=parcel_aspect,
            elevations=elevations,
        )
    else:
        shadow_res = shadow_engine.calculate_shadow_polygon(
            panel_width=p_width, panel_length=p_length,
            panel_tilt=new_target_tilt, panel_azimuth=new_target_azimuth,
            solar_elevation=pv_res["solar_elevation"],
            solar_azimuth=pv_res["solar_azimuth"],
            clearance_height=p_height,
            terrain_slope=parcel_slope,
            terrain_aspect=parcel_aspect,
        )
    stress_index = (context.get("biology") or {}).get("stress_index") or 0.0
    logger.info(
        "Tracker %s: target tilt=%.1f azimuth=%.1f -> shadow=%.2fm2 stress=%.2f",
        tracker_id, new_target_tilt, new_target_azimuth, shadow_res["area_m2"], stress_index,
    )

    intent_attrs = {
        "targetTilt": prop(new_target_tilt),
        "targetAzimuth": prop(new_target_azimuth),
        "controlStatus": prop(control_status),
    }
    state_attrs = {
        "tilt": prop(new_target_tilt),
        "azimuth": prop(new_target_azimuth),
        "modelRotation": prop([new_target_azimuth, -new_target_tilt, 0.0]),
        "controlStatus": prop(control_status),
    }

    ref_device = tracker.get("refDevice", {}).get("value") or tracker.get("refDevice")
    has_device = isinstance(ref_device, str) and bool(ref_device.strip())

    if not has_device:
        await orion.append_entity_attrs(tracker_id, {**intent_attrs, **state_attrs})
        return

    await orion.append_entity_attrs(tracker_id, intent_attrs)
    device_client = DeviceCommandClient()
    sent = await device_client.send_tracker_command(
        tenant_id, ref_device.strip(), new_target_tilt, new_target_azimuth
    )
    if not sent:
        raise RuntimeError(
            f"MQTT command failed for tracker {tracker_id} (device {ref_device.strip()})"
        )
    await orion.append_entity_attrs(tracker_id, state_attrs)
