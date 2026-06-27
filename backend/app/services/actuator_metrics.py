"""Actuator move cost and MPC economics for JSON Logic context."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from app.engines.pv_engine import PVEngine, PVSpec


def angular_distance_deg(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


def watts_per_degree() -> float:
    """Motor draw proxy (W per degree of combined tilt+azimuth travel)."""
    try:
        return float(os.getenv("ACTUATOR_WATTS_PER_DEGREE", "2.5"))
    except ValueError:
        return 2.5


def estimate_move_cost_wh(
    tilt_delta_deg: float,
    azimuth_delta_deg: float,
    *,
    watts_per_deg: float | None = None,
    move_duration_s: float = 30.0,
) -> float:
    """Estimate energy (Wh) to execute a move."""
    wpd = watts_per_deg if watts_per_deg is not None else watts_per_degree()
    travel = abs(tilt_delta_deg) + abs(azimuth_delta_deg) * 0.25
    power_w = travel * wpd
    return max(0.0, power_w * (move_duration_s / 3600.0))


def compute_mpc_economics(
    pv_engine: PVEngine,
    spec: PVSpec,
    current_tilt: float,
    current_azimuth: float,
    proposed_tilt: float,
    proposed_azimuth: float,
    ghi: float,
    dni: float,
    dhi: float,
    *,
    horizon_hours: float = 1.0,
    sim_time: datetime | None = None,
) -> dict[str, Any]:
    """Compare holding current orientation vs moving to proposed (1 h horizon)."""
    t = sim_time or datetime.utcnow()
    cur_spec = PVSpec(
        tilt=current_tilt,
        azimuth=current_azimuth,
        capacity_w=spec.capacity_w,
        module_area_m2=spec.module_area_m2,
    )
    prop_spec = PVSpec(
        tilt=proposed_tilt,
        azimuth=proposed_azimuth,
        capacity_w=spec.capacity_w,
        module_area_m2=spec.module_area_m2,
    )
    cur = pv_engine.calculate_expected_power(t, cur_spec, ghi, dni, dhi)
    tgt = pv_engine.calculate_expected_power(t, prop_spec, ghi, dni, dhi)

    cur_w = float(cur.get("expected_power_w", 0.0))
    tgt_w = float(tgt.get("expected_power_w", 0.0))
    gain_w = max(0.0, tgt_w - cur_w)
    gain_wh = gain_w * horizon_hours

    tilt_d = abs(proposed_tilt - current_tilt)
    az_d = angular_distance_deg(proposed_azimuth, current_azimuth)
    move_cost_wh = estimate_move_cost_wh(tilt_d, az_d)

    return {
        "current_power_w": round(cur_w, 2),
        "proposed_power_w": round(tgt_w, 2),
        "gain_power_w": round(gain_w, 2),
        "gain_wh_1h": round(gain_wh, 3),
        "net_gain_wh_1h": round(gain_wh - move_cost_wh, 3),
        "horizon_hours": horizon_hours,
    }


def build_actuator_context(
    current_tilt: float,
    current_azimuth: float,
    proposed_tilt: float,
    proposed_azimuth: float,
) -> dict[str, Any]:
    tilt_d = abs(proposed_tilt - current_tilt)
    az_d = angular_distance_deg(proposed_azimuth, current_azimuth)
    move_cost_wh = estimate_move_cost_wh(tilt_d, az_d)
    return {
        "tilt_delta_deg": round(tilt_d, 3),
        "azimuth_delta_deg": round(az_d, 3),
        "move_cost_wh": round(move_cost_wh, 4),
        "travel_deg": round(tilt_d + az_d * 0.25, 3),
    }
