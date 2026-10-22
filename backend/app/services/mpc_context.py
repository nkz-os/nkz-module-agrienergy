"""Enrich algorithm context with forecast, actuator cost, and MPC economics."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.engines.pv_engine import PVEngine, PVSpec
from app.services.actuator_metrics import (
    build_actuator_context,
    compute_mpc_economics,
)
from app.services.forecast_client import ForecastClient
from app.services.ngsi_helpers import ref_agri_parcel_from_entity


# Proposed orientation for economics gate (maximize preset default).
MPC_PROPOSED_TILT = 0.0
MPC_PROPOSED_AZIMUTH = 180.0


async def enrich_mpc_context(
    context: dict[str, Any],
    tracker: dict,
    tenant_id: str,
    lat: float,
    lon: float,
    current_tilt: float,
    current_azimuth: float,
    ghi: float,
    dni: float,
    dhi: float,
    capacity_w: float,
    module_area_m2: float,
) -> dict[str, Any]:
    """Add ``forecast``, ``actuator``, and ``economics`` groups (fail-safe)."""
    parcel_id = ref_agri_parcel_from_entity(tracker) or tracker.get(
        "hasAgriParcel", {}
    ).get("object", "")

    forecast_client = ForecastClient(tenant_id)
    try:
        if parcel_id:
            fc = await forecast_client.fetch_solar_1h(parcel_id, fallback_ghi=ghi)
        else:
            fc = {}
        if fc:
            context["forecast"] = fc
            ghi = float(fc.get("ghi_1h", ghi))
            dni = float(fc.get("dni_1h", dni))
            dhi = float(fc.get("dhi_1h", dhi))
    finally:
        await forecast_client.close()

    proposed_tilt = MPC_PROPOSED_TILT
    proposed_azimuth = MPC_PROPOSED_AZIMUTH
    context["actuator"] = build_actuator_context(
        current_tilt, current_azimuth, proposed_tilt, proposed_azimuth,
    )

    pv_engine = PVEngine(lat, lon)
    spec = PVSpec(
        tilt=current_tilt,
        azimuth=current_azimuth,
        capacity_w=capacity_w,
        module_area_m2=module_area_m2,
    )
    context["economics"] = compute_mpc_economics(
        pv_engine,
        spec,
        current_tilt,
        current_azimuth,
        proposed_tilt,
        proposed_azimuth,
        ghi,
        dni,
        dhi,
        sim_time=datetime.utcnow(),
    )
    return context
