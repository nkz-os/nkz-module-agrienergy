from typing import Any, Dict, Optional, Union

import logging
from json_logic import jsonLogic

logger = logging.getLogger(__name__)

# Algorithm can return: a number (tilt only), or a dict {"tilt": float, "azimuth": float}
AlgorithmResult = Optional[Union[float, Dict[str, float]]]


class AlgorithmEngine:
    """
    Motor de Evaluación de Algoritmos Autónomo.
    Permite inyectar reglas en formato JSON Logic para controlar dinámicamente el Tracker.
    La regla puede devolver:
    - Un número → se usa como targetTilt; azimuth se mantiene.
    - Un objeto {"tilt": n, "azimuth": m} → se usan ambos (claves opcionales).

    LIMITACIÓN (json-logic): un dict de UNA sola clave dentro de la regla
    (p.ej. {"tilt": 45}) se interpreta como operador, no como dato → la
    evaluación falla y se mantiene la orientación actual (fail-safe). Para
    devolver solo tilt desde una regla, usar {"tilt": 45, "azimuth": null}.
    Pineado en tests/test_algorithm_engine.py::test_partial_dict_tilt_only.
    """

    @staticmethod
    def evaluate_rule(logic: Dict[str, Any], context: Dict[str, Any]) -> AlgorithmResult:
        """
        Evalúa una regla JSON-Logic dado un contexto.
        Retorna: número (solo tilt), dict con "tilt" y/o "azimuth", o None (mantener actual).
        """
        try:
            result = jsonLogic(logic, context)
            if result is None or isinstance(result, bool):
                logger.debug("JSON Logic computed %s, keeping current orientation", result)
                return None
            if isinstance(result, (int, float)):
                return float(result)
            if isinstance(result, dict):
                out: Dict[str, float] = {}
                if "tilt" in result and result["tilt"] is not None:
                    try:
                        out["tilt"] = float(result["tilt"])
                    except (TypeError, ValueError):
                        pass
                if "azimuth" in result and result["azimuth"] is not None:
                    try:
                        out["azimuth"] = float(result["azimuth"])
                    except (TypeError, ValueError):
                        pass
                return out if out else None
            return None
        except Exception as e:
            logger.error("Failed to evaluate JSON Logic rule: %s", e)
            return None

    @staticmethod
    def resolve_orientation(
        result: AlgorithmResult,
        current_tilt: float,
        current_azimuth: float,
        rotation_axis: Optional[str] = None,
    ) -> tuple[float, float]:
        """
        Convert algorithm result to (tilt, azimuth). Applies rotation_axis when set:
        north_south or east_west → keep current azimuth; two_axis or None → use result.
        """
        if result is None:
            return (current_tilt, current_azimuth)
        if isinstance(result, (int, float)):
            return (float(result), current_azimuth)
        assert isinstance(result, dict)
        tilt = result.get("tilt")
        azimuth = result.get("azimuth")
        new_tilt = float(tilt) if tilt is not None else current_tilt
        new_azimuth = float(azimuth) if azimuth is not None else current_azimuth
        if rotation_axis in ("north_south", "east_west"):
            new_azimuth = current_azimuth
        return (new_tilt, new_azimuth)
        
    @staticmethod
    def default_algorithm() -> Dict[str, Any]:
        """
        Default rule: GHI > 10 -> tilt 0, else -60 (standby).
        """
        return {
            "if": [
                {">": [{"var": "weather.ghi"}, 10]},
                0,
                -60,
            ]
        }

    @staticmethod
    def builtin_algorithms() -> list[Dict[str, Any]]:
        """Built-in algorithm presets (id, name, logic) for GET /algorithms. Use var with default for fail-safe."""
        return [
            {
                "id": "default:maximize",
                "name": "Maximize production (GHI threshold)",
                "logic": {
                    "if": [
                        {">": [{"var": ["weather.ghi", 0]}, 10]},
                        {"tilt": 0, "azimuth": 180},
                        {"tilt": -60, "azimuth": 180},
                    ]
                },
            },
            {
                "id": "default:hierarchical_failsafe",
                "name": "Hierarchical fail-safe (wind > stress > GHI > standby)",
                "logic": {
                    "if": [
                        {">": [{"var": ["weather.wind_speed", 999]}, 15]},
                        {"tilt": 0, "azimuth": 180},
                        {">": [{"var": ["biology.stress_index", 0]}, 0.8]},
                        {"tilt": 70, "azimuth": 180},
                        {">": [{"var": ["weather.ghi", 0]}, 10]},
                        {"tilt": 0, "azimuth": 180},
                        {"tilt": -60, "azimuth": 180},
                    ]
                },
            },
            {
                "id": "default:wind_storm_stow",
                "name": "Wind storm stow (degraded or wind > 15 m/s -> flat)",
                "logic": {
                    "if": [
                        {"==": [{"var": ["control.degraded", False]}, True]},
                        {"tilt": 0, "azimuth": None},
                        {">": [{"var": ["weather.wind_speed", -1]}, 15]},
                        {"tilt": 0, "azimuth": None},
                        {"tilt": 0, "azimuth": 180},
                    ]
                },
            },
            {
                "id": "thermal_stress",
                "name": "Thermal stress mitigation (T_extreme > 35°C -> shade 70°)",
                "logic": {
                    "if": [
                        {">": [{"var": ["weather.temperature", 20]}, 35]},
                        {"tilt": 70, "azimuth": 180},
                        {"tilt": 0, "azimuth": 180},
                    ]
                },
            },
            {
                "id": "wind_barrier",
                "name": "Wind barrier (wind_speed > 15 m/s -> tilt 75°)",
                "logic": {
                    "if": [
                        {">": [{"var": ["weather.wind_speed", 999]}, 15]},
                        {"tilt": 75, "azimuth": 180},
                        {"tilt": 0, "azimuth": 180},
                    ]
                },
            },
            {
                "id": "frost_prevention",
                "name": "Frost prevention (leaf_temperature <= 2°C -> tilt 0°)",
                "logic": {"if": [{"<=": [{"var": ["sensors.leaf_temperature", 10]}, 2]}, 0, {"var": "tracker.tilt"}]},
            },
            {
                "id": "hydric_stress",
                "name": "Hydric stress (LSTM stress_index > 0.8 -> shade 70°)",
                "logic": {
                    "if": [
                        {">": [{"var": ["biology.stress_index", 0]}, 0.8]},
                        {"tilt": 70, "azimuth": 180},
                        {"tilt": -60, "azimuth": 180},
                    ]
                },
            },
            {
                "id": "par_optimization",
                "name": "PAR optimization (par_under_panel < 800 -> standby -60°)",
                "logic": {"if": [{"<": [{"var": ["sensors.par_under_panel", 1000]}, 800]}, -60, {"var": "tracker.tilt"}]},
            },
            {
                "id": "default:mpc_hold",
                "name": "MPC hold (move only if net Wh gain > actuator cost)",
                "logic": {
                    "if": [
                        {"==": [{"var": ["control.degraded", False]}, True]},
                        {"tilt": 0, "azimuth": None},
                        {">": [{"var": ["weather.ghi", 0]}, 10]},
                        {
                            "if": [
                                {">": [
                                    {"var": ["economics.net_gain_wh_1h", 0]},
                                    {"var": ["actuator.move_cost_wh", 1]},
                                ]},
                                {"tilt": 0, "azimuth": 180},
                                {"tilt": None, "azimuth": None},
                            ]
                        },
                        {"tilt": -60, "azimuth": 180},
                    ]
                },
            },
        ]
