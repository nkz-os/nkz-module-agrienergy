# AgriEnergy — Reference

Single reference for algorithms, simulation, and integrations. The repo is public; this doc is the main technical entry point.

---

## 1. Algorithms

**Selection**: GET `/api/agrienergy/algorithms` returns presets; the UI dropdown sends PATCH `/api/agrienergy/trackers/{id}/algorithm` with `{ "activeAlgorithm": { "id": "<preset_id>" } }`. Stored in the tracker’s `activeAlgorithm` (NGSI-LD).

**Built-in presets** (all use fail-safe `{"var": ["path", default]}` and return `{ "tilt", "azimuth" }`):

| Id | Name | Logic (summary) |
|----|------|-----------------|
| default:maximize | Maximize production | GHI > 10 → 0°; else -60°. |
| default:hierarchical_failsafe | Hierarchical fail-safe (recommended) | Wind > 15 → 0°; stress_index > 0.8 → 70°; GHI > 10 → 0°; else -60°. |
| default:wind_storm_stow | Wind storm stow | `control.degraded` or wind > 15 m/s → flat; else track. |
| default:mpc_hold | MPC hold | Degraded → stow; GHI > 10 → move only if `economics.net_gain_wh_1h > actuator.move_cost_wh`; else hold; low sun → -60°. |
| thermal_stress | Thermal stress (T > 35°C) | Shade 70°; else 0°. |
| wind_barrier | Wind barrier (> 15 m/s) | Tilt 75°; else 0°. |
| hydric_stress | Hydric stress (LSTM) | stress_index > 0.8 → 70°; else -60°. |
| frost_prevention | Frost (leaf_temperature ≤ 2°C) | Tilt 0°; else keep current. |
| par_optimization | PAR under panel < 800 | Standby -60°; else keep current. |

**MPC context** (enriched on `/notify` when not in forced stow): `forecast.*` (1 h GHI/DNI/DHI), `actuator.*` (move cost Wh), `economics.*` (`net_gain_wh_1h`). See README § Predictive control (MPC).

**Adding a new algorithm**: (1) Ensure data is in context (signalMapping for sensors; crop-health for biology.*). (2) Write JSON Logic with `var` + default and return `{ "tilt", "azimuth" }`. (3) Add an entry to `AlgorithmEngine.builtin_algorithms()` in `backend/app/engines/algorithm_engine.py`.

**Tracker attribute** `rotationAxis` (optional): `north_south` | `east_west` | `two_axis`. When set, single-axis trackers keep current azimuth; only tilt is applied from the rule.

---

## 2. Simulation

- **One-shot**: POST `/api/agrienergy/simulate` — tracker, parcel, telemetry, target_tilt → expected_power_w, shadow_area_m2, shadow_polygon_2d.
- **Period**: POST `/api/agrienergy/simulate-period` — start, end, resolution, series (payload); returns time series of tilt, azimuth, expected_power_w, shadow_area_m2, optional stress_index. **Full contract**: [SIMULATE_PERIOD_SPEC.md](SIMULATE_PERIOD_SPEC.md) (limits when `include_biology`, O(1) series lookup, state carry-over).

---

## 3. Biology (crop-health water stress)

In the /notify flow AgriEnergy reads the parcel's `CropHealthAssessment` from Orion-LD (the tracker's `hasAgriParcel` / `refAgriParcel`). `context["biology"] = {"stress_index": x}` only when `underPanelWaterStressFidelity` is `iot_sensor`, `underPanelWaterStressObservedAt` is at most `WATER_STRESS_MAX_AGE_S` old (default 3600) and the index is in [0, 1].

- **Fail-safe**: in every other case (no parcel, no state, other fidelity, stale) `context["biology"] = {}`. Rules use `{"var": ["biology.stress_index", 0]}` for defaults.

---

## 4. Odoo / N8N (energy communities)

See **[ODOO_N8N_AGRIENERGY.md](ODOO_N8N_AGRIENERGY.md)** for the full webhook contract and Wh calculation spec.

**FinBridgeEmitter** POSTs to N8N with `tenant_id`, `tracker_id`, `date`, `generation_wh`, `consumption_wh`, `surplus_wh`, `module`. URL: `AGRIENERGY_N8N_WEBHOOK_URL`.

**Daily job (Phase 8.2):** K8s CronJob `agrienergy-daily-aggregation` runs trapezoidal integration over `measuredPowerW` / `powerW` via timeseries-reader, emits FinBridge, writes `dailyGenerationWh` on the tracker in Orion-LD.
