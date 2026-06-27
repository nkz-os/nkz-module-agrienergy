"""Tests for actuator move cost and MPC economics."""

from app.engines.pv_engine import PVEngine, PVSpec
from app.services.actuator_metrics import (
    build_actuator_context,
    compute_mpc_economics,
    estimate_move_cost_wh,
)


def test_move_cost_zero_when_no_travel():
    assert estimate_move_cost_wh(0.0, 0.0) == 0.0


def test_move_cost_increases_with_travel():
    low = estimate_move_cost_wh(5.0, 0.0, watts_per_deg=2.0, move_duration_s=60.0)
    high = estimate_move_cost_wh(30.0, 90.0, watts_per_deg=2.0, move_duration_s=60.0)
    assert high > low > 0.0


def test_actuator_context_keys():
    ctx = build_actuator_context(10.0, 170.0, 0.0, 180.0)
    assert "move_cost_wh" in ctx
    assert ctx["tilt_delta_deg"] == 10.0


def test_mpc_economics_net_gain():
    pv = PVEngine(42.8, -1.6)
    spec = PVSpec(tilt=30.0, azimuth=180.0, capacity_w=500.0, module_area_m2=8.0)
    eco = compute_mpc_economics(
        pv, spec,
        current_tilt=30.0, current_azimuth=180.0,
        proposed_tilt=0.0, proposed_azimuth=180.0,
        ghi=800.0, dni=500.0, dhi=200.0,
        horizon_hours=1.0,
    )
    assert "net_gain_wh_1h" in eco
    assert eco["gain_wh_1h"] >= 0.0
