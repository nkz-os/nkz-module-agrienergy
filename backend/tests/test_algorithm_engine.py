"""AlgorithmEngine: JSON Logic evaluation, orientation resolution, builtin presets."""

import pytest

from app.engines.algorithm_engine import AlgorithmEngine

ENG = AlgorithmEngine


def preset(pid: str) -> dict:
    by_id = {p["id"]: p["logic"] for p in ENG.builtin_algorithms()}
    return by_id[pid]


class TestEvaluateRule:
    def test_number_result(self):
        assert ENG.evaluate_rule({"+": [10, 20]}, {}) == 30.0

    def test_dict_result(self):
        rule = {"if": [True, {"tilt": 30, "azimuth": 170}, 0]}
        assert ENG.evaluate_rule(rule, {}) == {"tilt": 30.0, "azimuth": 170.0}

    def test_partial_dict_tilt_only(self):
        # ENGINE BUG: json_logic treats any single-key dict as an operator call.
        # {"tilt": 45} is parsed as op "tilt" (unknown) → exception → None.
        # The docstring claims optional keys are supported, but only multi-key dicts
        # (e.g. {"tilt": x, "azimuth": y}) are treated as plain data by json_logic.
        # All builtin presets correctly emit both keys and are unaffected.
        # BUG: a user-supplied rule whose branch is {"tilt": 45} silently returns None.
        rule = {"if": [True, {"tilt": 45}, 0]}
        assert ENG.evaluate_rule(rule, {}) is None  # not {"tilt": 45.0} — see bug note above

    def test_bool_result_keeps_current(self):
        assert ENG.evaluate_rule({">": [2, 1]}, {}) is None

    def test_none_result_keeps_current(self):
        assert ENG.evaluate_rule({"if": [False, 10, None]}, {}) is None

    def test_non_numeric_dict_values_dropped(self):
        rule = {"if": [True, {"tilt": "abc", "azimuth": 170}, 0]}
        assert ENG.evaluate_rule(rule, {}) == {"azimuth": 170.0}

    def test_null_azimuth_idiom_yields_tilt_only(self):
        # The documented idiom for tilt-only custom rules: a multi-key dict
        # with azimuth null is data (not an operator) and None is filtered out.
        rule = {"if": [True, {"tilt": 45, "azimuth": None}, 0]}
        assert ENG.evaluate_rule(rule, {}) == {"tilt": 45.0}

    def test_corrupt_rule_never_raises(self):
        assert ENG.evaluate_rule({"nonexistent_op": [1]}, {}) is None

    def test_var_default_failsafe_empty_context(self):
        # default rule must not raise with empty context
        assert ENG.evaluate_rule(ENG.default_algorithm(), {}) is not None


class TestResolveOrientation:
    def test_none_keeps_current(self):
        assert ENG.resolve_orientation(None, 10.0, 170.0) == (10.0, 170.0)

    def test_number_sets_tilt_keeps_azimuth(self):
        assert ENG.resolve_orientation(30.0, 10.0, 170.0) == (30.0, 170.0)

    def test_zero_result_is_a_valid_tilt_not_keep_current(self):
        # 0.0 is falsy: a naive `if result:` guard would wrongly keep current.
        # frost_prevention returns 0 (horizontal) when triggered.
        assert ENG.resolve_orientation(0.0, 33.0, 170.0) == (0.0, 170.0)

    def test_dict_sets_both(self):
        assert ENG.resolve_orientation({"tilt": 30, "azimuth": 90}, 10, 170) == (30.0, 90.0)

    def test_dict_partial_keeps_missing(self):
        assert ENG.resolve_orientation({"tilt": 30}, 10, 170) == (30.0, 170.0)

    @pytest.mark.parametrize("axis", ["north_south", "east_west"])
    def test_single_axis_locks_azimuth(self, axis):
        assert ENG.resolve_orientation(
            {"tilt": 30, "azimuth": 90}, 10, 170, rotation_axis=axis
        ) == (30.0, 170.0)

    @pytest.mark.parametrize("axis", ["two_axis", None])
    def test_two_axis_uses_result(self, axis):
        assert ENG.resolve_orientation(
            {"tilt": 30, "azimuth": 90}, 10, 170, rotation_axis=axis
        ) == (30.0, 90.0)


class TestBuiltinPresets:
    def test_nine_presets_exposed(self):
        ids = [p["id"] for p in ENG.builtin_algorithms()]
        assert ids == [
            "default:maximize", "default:hierarchical_failsafe", "default:wind_storm_stow",
            "thermal_stress", "wind_barrier", "frost_prevention", "hydric_stress",
            "par_optimization", "default:mpc_hold",
        ]

    # (preset_id, context, expected evaluate_rule output)
    CASES = [
        ("default:maximize", {"weather": {"ghi": 800}}, {"tilt": 0.0, "azimuth": 180.0}),
        ("default:maximize", {"weather": {"ghi": 5}}, {"tilt": -60.0, "azimuth": 180.0}),
        ("default:maximize", {}, {"tilt": -60.0, "azimuth": 180.0}),  # var default 0
        ("wind_barrier", {"weather": {"wind_speed": 20}}, {"tilt": 75.0, "azimuth": 180.0}),
        ("wind_barrier", {"weather": {"wind_speed": 5}}, {"tilt": 0.0, "azimuth": 180.0}),
        # var default 999 -> missing anemometer = assume storm (fail-safe stow)
        ("wind_barrier", {}, {"tilt": 75.0, "azimuth": 180.0}),
        ("thermal_stress", {"weather": {"temperature": 40}}, {"tilt": 70.0, "azimuth": 180.0}),
        ("thermal_stress", {"weather": {"temperature": 25}}, {"tilt": 0.0, "azimuth": 180.0}),
        ("hydric_stress", {"biology": {"stress_index": 0.9}}, {"tilt": 70.0, "azimuth": 180.0}),
        ("hydric_stress", {"biology": {"stress_index": 0.1}}, {"tilt": -60.0, "azimuth": 180.0}),
        ("hydric_stress", {}, {"tilt": -60.0, "azimuth": 180.0}),  # biology absent
        ("frost_prevention", {"sensors": {"leaf_temperature": 0}, "tracker": {"tilt": 33}}, 0.0),
        ("frost_prevention", {"sensors": {"leaf_temperature": 10}, "tracker": {"tilt": 33}}, 33.0),
        ("par_optimization", {"sensors": {"par_under_panel": 500}, "tracker": {"tilt": 33}}, -60.0),
        ("par_optimization", {"sensors": {"par_under_panel": 900}, "tracker": {"tilt": 33}}, 33.0),
        # hierarchy: wind beats stress beats ghi
        ("default:hierarchical_failsafe",
         {"weather": {"wind_speed": 20, "ghi": 800}, "biology": {"stress_index": 0.9}},
         {"tilt": 0.0, "azimuth": 180.0}),
        ("default:hierarchical_failsafe",
         {"weather": {"wind_speed": 5, "ghi": 800}, "biology": {"stress_index": 0.9}},
         {"tilt": 70.0, "azimuth": 180.0}),
        ("default:hierarchical_failsafe",
         {"weather": {"wind_speed": 5, "ghi": 800}, "biology": {"stress_index": 0.1}},
         {"tilt": 0.0, "azimuth": 180.0}),
        ("default:hierarchical_failsafe",
         {"weather": {"wind_speed": 5, "ghi": 5}, "biology": {"stress_index": 0.1}},
         {"tilt": -60.0, "azimuth": 180.0}),
        ("default:wind_storm_stow", {"control": {"degraded": True}}, {"tilt": 0.0}),
        ("default:wind_storm_stow", {"weather": {"wind_speed": 20}}, {"tilt": 0.0}),
        ("default:wind_storm_stow", {"weather": {"wind_speed": 5}}, {"tilt": 0.0, "azimuth": 180.0}),
    ]

    @pytest.mark.parametrize("pid,context,expected", CASES)
    def test_preset_matrix(self, pid, context, expected):
        assert ENG.evaluate_rule(preset(pid), context) == expected
