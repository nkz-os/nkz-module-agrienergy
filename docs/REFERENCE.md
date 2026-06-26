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
| thermal_stress | Thermal stress (T > 35°C) | Shade 70°; else 0°. |
| wind_barrier | Wind barrier (> 15 m/s) | Tilt 75°; else 0°. |
| hydric_stress | Hydric stress (LSTM) | stress_index > 0.8 → 70°; else -60°. |
| frost_prevention | Frost (leaf_temperature ≤ 2°C) | Tilt 0°; else keep current. |
| par_optimization | PAR under panel < 800 | Standby -60°; else keep current. |

**Adding a new algorithm**: (1) Ensure data is in context (signalMapping for sensors; Intelligence for biology.*). (2) Write JSON Logic with `var` + default and return `{ "tilt", "azimuth" }`. (3) Add an entry to `AlgorithmEngine.builtin_algorithms()` in `backend/app/engines/algorithm_engine.py`.

**Tracker attribute** `rotationAxis` (optional): `north_south` | `east_west` | `two_axis`. When set, single-axis trackers keep current azimuth; only tilt is applied from the rule.

---

## 2. Simulation

- **One-shot**: POST `/api/agrienergy/simulate` — tracker, parcel, telemetry, target_tilt → expected_power_w, shadow_area_m2, shadow_polygon_2d.
- **Period**: POST `/api/agrienergy/simulate-period` — start, end, resolution, series (payload); returns time series of tilt, azimuth, expected_power_w, shadow_area_m2, optional stress_index. **Full contract**: [SIMULATE_PERIOD_SPEC.md](SIMULATE_PERIOD_SPEC.md) (limits when `include_biology`, O(1) series lookup, state carry-over).

---

## 3. Intelligence (scalar bundle)

AgriEnergy calls **POST /api/intelligence/evaluate_status** in the /notify flow (after building context and shadow). Request: tracker_id, parcel_id, timestamp, shadow_polygon_2d, telemetry. Response: scalar bundle (e.g. stress_index) → injected as `context["biology"]`.

- **Timeout**: 200 ms. Intelligence must respond via fast read (e.g. Redis cache), not on-demand LSTM in the request.
- **Fail-safe**: On timeout/5xx, AgriEnergy sets `context["biology"] = {}`. Rules use `{"var": ["biology.stress_index", 0]}` for defaults.

The Intelligence module (evaluate_status, worker, Redis) is implemented and maintained by a separate team; this contract is the interface.

---

## 4. Odoo / N8N (energy communities)

See **[ODOO_N8N_AGRIENERGY.md](ODOO_N8N_AGRIENERGY.md)** for the full webhook contract and Wh calculation spec.

**FinBridgeEmitter** POSTs to N8N with `tenant_id`, `tracker_id`, `date`, `generation_wh`, `consumption_wh`, `surplus_wh`, `module`. URL: `AGRIENERGY_N8N_WEBHOOK_URL`.

**Daily job (Phase 8.2):** K8s CronJob `agrienergy-daily-aggregation` runs trapezoidal integration over `measuredPowerW` / `powerW` via timeseries-reader, emits FinBridge, writes `dailyGenerationWh` on the tracker in Orion-LD.

**Intelligence push (P3-2):** Owned by the Intelligence module (pre-computed Redis bundle). AgriEnergy keeps the 200 ms read-only contract in `/notify`; no change required here.
