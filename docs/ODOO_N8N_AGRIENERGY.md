# AgriEnergy → N8N → Odoo (FinBridge)

Energy communities integration: daily generation Wh per tracker flows to Odoo via N8N.

## Webhook contract

**Endpoint:** `POST {AGRIENERGY_N8N_WEBHOOK_URL}` (default in-cluster: `http://n8n-webhook-service:5678/webhook/agrienergy-aggregation`)

**Payload (JSON):**

| Field | Type | Description |
|-------|------|-------------|
| `tenant_id` | string | FIWARE tenant (hyphen-canonical) |
| `tracker_id` | string | `AgriEnergyTracker` entity URN |
| `date` | string | UTC day `YYYY-MM-DD` |
| `generation_wh` | number | Integrated energy (watt-hours) |
| `consumption_wh` | number | Site consumption (0 until meter mapped) |
| `surplus_wh` | number | `generation_wh - consumption_wh` |
| `module` | string | Always `agrienergy` |

N8N workflow should forward to Odoo webhook event `odoo.energy.log` with installation/meter id and kWh value.

## How `generation_wh` is computed (canonical — software path)

AgriEnergy does **not** read inverter totals directly. It integrates **instantaneous power (W)** from the platform timeseries store:

1. **Source:** `timeseries-reader` v2 API — telemetry for the tracker URN, or its `refDevice` if the inverter publishes there.
2. **Attributes tried (in order):** `measuredPowerW`, `powerW`, `measured_w`, `power_w`.
3. **Window:** previous UTC calendar day `[00:00, 24:00)`.
4. **Method:** trapezoidal rule over consecutive samples; negative W clamped to 0 (generation-only).
5. **Minimum data:** at least 2 samples in the window; otherwise the tracker is skipped (no FinBridge emit).
6. **Orion snapshot:** `dailyGenerationWh` + `dailyGenerationDate` Properties appended on the tracker (metadata, not timeseries).

**Platform prerequisite:** power measurement keys must be whitelisted for telemetry reads. In gitops, extend timeseries-reader:

```yaml
TIMESERIES_V2_TELEMETRY_ATTR_WHITELIST_EXTRA: "measuredPowerW,powerW"
```

## Scheduler

- **CronJob:** `k8s/cronjob-daily-aggregation.yaml` — runs `python3 -m app.daily_aggregation` at 00:05 UTC.
- **Manual / replay:** `POST /api/agrienergy/internal/daily-aggregation?tenant_id=...&day=YYYY-MM-DD` with header `X-Internal-Service-Secret`.

## Worker authentication

The cron pod calls `timeseries-reader` over HTTP (no direct Postgres timeseries access). Required env:

| Variable | Purpose |
|----------|---------|
| `WORKER_BEARER_TOKEN` | Service-account JWT (Keycloak client credentials) |
| `HMAC_SECRET` | `X-Auth-Signature` for timeseries-reader (`{sig}:{ts}`) |
| `TIMESERIES_READER_URL` | Internal service URL |

Tenant discovery: `AGGREGATION_TENANTS` override, else `tenant_installed_modules` where `module_id = 'agrienergy'`.

## Hardware alternative (future)

If the inverter exposes **cumulative energy (Wh/kWh)** as a monotonic counter, a separate ingest path may replace the integral. Until then, the trapezoidal software path is the production default.
