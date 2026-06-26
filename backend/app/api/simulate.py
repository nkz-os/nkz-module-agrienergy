"""PV + shadow simulation endpoint (sandbox)."""

from datetime import datetime

from fastapi import APIRouter

from app.engines.elevation import ElevationService
from app.engines.pv_engine import PVEngine, PVSpec
from app.engines.shadow_engine import ShadowEngine
from app.models import SimulationRequest, SimulationResponse

router = APIRouter(tags=["AgriEnergy Orchestrator"])


@router.post("/simulate", response_model=SimulationResponse)
async def simulate(request: SimulationRequest):
    """One-shot PV + shadow simulation for a tracker/parcel and target tilt."""
    parcel = request.parcel
    telemetry = request.telemetry
    target_tilt = request.target_tilt

    try:
        sim_time = datetime.fromisoformat(telemetry.timestamp.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        sim_time = datetime.utcnow()

    shadow_engine = ShadowEngine()

    if request.panel_array is not None:
        arr = request.panel_array
        if not arr.positions:
            return SimulationResponse(expected_power_w=0.0, shadow_area_m2=0.0, shadow_polygon_2d=[])

        ref = arr.positions[0]
        pv_engine = PVEngine(ref.lat, ref.lon)
        total_area_m2 = arr.panel_width * arr.panel_length * len(arr.positions)
        total_capacity_w = 500.0 * len(arr.positions)

        pv_res = pv_engine.calculate_expected_power(
            sim_time,
            PVSpec(
                tilt=target_tilt, azimuth=telemetry.actual_azimuth,
                capacity_w=total_capacity_w, module_area_m2=total_area_m2,
            ),
            telemetry.ghi, telemetry.dni, telemetry.dhi,
        )
        positions = [(p.lon, p.lat) for p in arr.positions]
        elevation_svc = ElevationService(tenant_id="")
        elevations = await elevation_svc.get_elevations(positions, parcel_id=parcel.id)
        shadow_res = shadow_engine.calculate_array_shadow(
            panel_positions=positions,
            panel_width=arr.panel_width,
            panel_length=arr.panel_length,
            panel_tilt=target_tilt,
            panel_azimuth=telemetry.actual_azimuth,
            solar_elevation=pv_res["solar_elevation"],
            solar_azimuth=pv_res["solar_azimuth"],
            clearance_height=arr.clearance_height,
            terrain_slope=parcel.slope,
            terrain_aspect=parcel.aspect,
            elevations=elevations,
        )
        polygon_list = list(shadow_res["polygon"]) if shadow_res["polygon"] else []
        return SimulationResponse(
            expected_power_w=round(pv_res["expected_power_w"], 2),
            shadow_area_m2=round(shadow_res["area_m2"], 4),
            shadow_polygon_2d=polygon_list,
        )

    tracker = request.tracker
    pv_engine = PVEngine(tracker.lat, tracker.lon)
    spec = PVSpec(
        tilt=target_tilt,
        azimuth=telemetry.actual_azimuth,
        capacity_w=tracker.capacity_w,
        module_area_m2=tracker.panel_width * tracker.panel_length,
    )
    pv_res = pv_engine.calculate_expected_power(
        sim_time, spec, telemetry.ghi, telemetry.dni, telemetry.dhi,
    )
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
