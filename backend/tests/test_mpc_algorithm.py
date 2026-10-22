"""Tests for MPC algorithm preset."""

from app.engines.algorithm_engine import AlgorithmEngine

ENG = AlgorithmEngine


def preset(pid: str) -> dict:
    by_id = {p["id"]: p["logic"] for p in ENG.builtin_algorithms()}
    return by_id[pid]


def test_mpc_hold_moves_when_gain_exceeds_cost():
    ctx = {
        "weather": {"ghi": 500},
        "economics": {"net_gain_wh_1h": 50.0},
        "actuator": {"move_cost_wh": 5.0},
        "tracker": {"tilt": 30.0},
    }
    result = ENG.evaluate_rule(preset("default:mpc_hold"), ctx)
    assert result == {"tilt": 0.0, "azimuth": 180.0}


def test_mpc_hold_keeps_current_when_gain_low():
    ctx = {
        "weather": {"ghi": 500},
        "economics": {"net_gain_wh_1h": 1.0},
        "actuator": {"move_cost_wh": 10.0},
        "tracker": {"tilt": 30.0},
    }
    result = ENG.evaluate_rule(preset("default:mpc_hold"), ctx)
    assert result is None  # hold — resolve_orientation keeps current


def test_mpc_hold_stow_when_degraded():
    ctx = {
        "control": {"degraded": True},
        "weather": {"ghi": 500},
        "economics": {"net_gain_wh_1h": 100.0},
    }
    result = ENG.evaluate_rule(preset("default:mpc_hold"), ctx)
    assert result == {"tilt": 0.0}
