# AgriEnergy Orchestrator — Nekazari Module

Agrivoltaic module: PV simulation (pvlib), 2.5D shadow geometry (Shapely), JSON Logic algorithms, NGSI-LD closed-loop (notify → algorithm → targetTilt), and optional biological handshake (NKZ-Intelligence) and FinBridge (N8N) aggregation.

Built from the Nekazari module template: single IIFE bundle uploaded to MinIO, loaded at runtime by the host.

---

## Backend API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | — | K8s liveness/readiness probe |
| POST | `/api/agrienergy/simulate` | — | One-shot PV + shadow simulation (tracker, parcel, telemetry, target_tilt) → expected_power_w, shadow_area_m2, shadow_polygon_2d |
| POST | `/api/agrienergy/notify` | tenant | NGSI-LD subscription webhook (WeatherObserved / AgriEnergyTracker) — runs algorithm, updates targetTilt/tilt/modelRotation, optional MQTT command |
| GET | `/api/agrienergy/status?tracker_id=...` | tenant | Instant values for panel/Cesium: orientation, power, sensors, timestamp |
| GET | `/api/agrienergy/algorithms` | tenant | List built-in algorithm presets (id, name, logic) for selector |
| GET | `/api/agrienergy/signal-sources` | tenant | List entities and numeric attributes for signal mapping (query: `entity_types`) |
| PATCH | `/api/agrienergy/trackers/{id}/signal-mapping` | tenant | Save signal mapping (body: `{ "signalMapping": [ { "contextKey", "entityId", "attribute" } ] }`) |
| PATCH | `/api/agrienergy/trackers/{id}/algorithm` | tenant | Set active algorithm (body: `{ "activeAlgorithm": { "id": "default:maximize" } }` or full JSON Logic) |
| GET | `/api/agrienergy/parcels` | tenant | List parcels (AgriParcel) for create-park dropdown |
| GET | `/api/agrienergy/parks` | tenant | List solar parks (AgriSolarPark); includes tracker_count per park |
| GET | `/api/agrienergy/parks/{park_id}/trackers` | tenant | List trackers in that park (same refAgriParcel) |
| POST | `/api/agrienergy/parks` | tenant | Create AgriSolarPark (body: `{ "name", "ref_agri_parcel" }`). Requires `CONTEXT_BROKER_URL`. |
| GET | `/api/agrienergy/admin/stats` | TenantAdmin / PlatformAdmin | Module stats (placeholder counts; extend later) |
| GET | `/api/agrienergy/docs` | — | OpenAPI Swagger UI |
| GET | `/api/agrienergy/openapi.json` | — | OpenAPI schema |

**Documentation**: [docs/REFERENCE.md](docs/REFERENCE.md) — algorithms (catalogue + how to add), simulation, Intelligence contract, Odoo/N8N. [docs/SIMULATE_PERIOD_SPEC.md](docs/SIMULATE_PERIOD_SPEC.md) — full contract for POST /simulate-period.

**Signal configuration**: Map sensors (NGSI-LD entities) per tracker via "Configure signals" UI: GET `/status`, GET `/signal-sources`, PATCH signal-mapping. See REFERENCE.md.

Ensure ingress routes `/api/agrienergy` to `agrienergy-api-service:8000` before the generic `/api` catch-all.

---

## Quick start

```bash
git clone https://github.com/nkz-os/nkz-module-agrienergy.git
cd nkz-module-agrienergy
npm install
```

Configure environment (see SETUP.md for optional placeholders if you fork this repo to create another module).

---

## Structure

```
my-module/
├── src/
│   ├── moduleEntry.ts          # IIFE entry — calls window.__NKZ__.register()
│   ├── slots/index.ts          # Declare which host slots you occupy
│   ├── components/slots/       # Slot React components
│   ├── hooks/                  # Custom hooks
│   ├── services/               # API client
│   └── types/global.d.ts       # Host globals (window.__NKZ__, etc.)
├── backend/                    # FastAPI backend (optional, delete if unused)
├── k8s/
│   ├── backend-deployment.yaml # K8s Deployment + Service for backend
│   └── registration.sql        # Insert/update marketplace_modules
├── manifest.json               # Module metadata
├── vite.config.ts              # Uses @nekazari/module-builder preset
└── dist/nkz-module.js          # Build output — upload this to MinIO
```

---

## Build

```bash
npm run build:module
# → dist/nkz-module.js  (~50–300 KB depending on your dependencies)
```

The `@nekazari/module-builder` preset enforces:
- **IIFE format** — single self-executing bundle
- **Classic JSX runtime** — `React.createElement()`, not `_jsx()` (required for UMD React global)
- **Externalized dependencies** — React, ReactDOM, react-router-dom, @nekazari/sdk, @nekazari/ui-kit are mapped to window globals provided by the host. Never bundle them.

---

## Deploy

### 1. Upload bundle to MinIO

```bash
# From the server (port-forward MinIO first):
sudo kubectl port-forward -n nekazari svc/minio-service 9000:9000 &
mc alias set minio http://localhost:9000 minioadmin minioadmin
mc cp dist/nkz-module.js minio/nekazari-frontend/modules/agrienergy/nkz-module.js \
   --attr "Content-Type=application/javascript"
```

Never write directly to MinIO's `/data/` filesystem — use the S3 API.

### 2. Register in the database

```bash
# Run registration.sql once per environment:
kubectl exec -n nekazari deployment/postgresql -- \
  psql -U postgres -d nekazari -f /tmp/registration.sql
```

Or insert manually and update `remote_entry_url = '/modules/agrienergy/nkz-module.js'`.

### 3. Deploy backend (if your module has one)

```bash
docker build -t ghcr.io/nkz-os/agrienergy-backend:v1.0.0 ./backend
docker push ghcr.io/nkz-os/agrienergy-backend:v1.0.0
kubectl apply -f k8s/backend-deployment.yaml -n nekazari
```

Add an ingress rule routing `/api/agrienergy` → `agrienergy-api-service:8000` before the generic `/api` catch-all.

---

## Slots

Edit `src/slots/index.ts` to register your components in host slots:

| Slot | Where it renders |
|------|-----------------|
| `context-panel` | Side panel when an entity is selected |
| `bottom-panel` | Tabbed panel at the bottom of the viewer |
| `map-layer` | Overlay or toolbar button on the 3D map |
| `layer-toggle` | Toggle entry in the layer panel |
| `entity-tree` | Context menu in the entity tree |
| `dashboard-widget` | Card in the tenant dashboard |

---

## Build rules (critical)

- **JSX runtime must be `classic`** — `tsconfig.json` has `"jsx": "react"` and vite preset uses `jsxRuntime: 'classic'`. The automatic runtime emits `_jsx()` which doesn't exist on the UMD `window.React` global.
- **Never bundle externalized deps** — React, ReactDOM, react-router-dom, @nekazari/sdk, @nekazari/ui-kit. They come from the host. Bundling them creates two React instances and breaks hooks.
- **Web workers must use `?worker&inline`** — e.g. `import MyWorker from './worker?worker&inline'`. Without `&inline`, Vite generates a separate file with an absolute path that breaks when loaded from MinIO.
- **No Module Federation** — the host uses IIFE-only loading. `@originjs/vite-plugin-federation` is dead, do not use it.

---

## Local development

```bash
npm run dev
# Starts a Vite dev server at http://localhost:5003
# Full integration (slots, auth) requires the host app.
# Set VITE_PROXY_TARGET=https://your-api-domain in .env to proxy API calls.
```

Copy `env.example` to `.env` and fill in your values.

---

## DataHub compatibility

If your module collects timeseries data, the DataHub module can visualise it in a Data Canvas without extra frontend work.

- **Data in platform TimescaleDB**: nothing needed — DataHub finds it automatically.
- **Data in an external system**: implement a `GET /api/timeseries/entities/{id}/data` endpoint returning **Apache Arrow IPC** (`float64` epoch seconds, `float64` value), declare `source` in the NGSI-LD entity attribute, and set `TIMESERIES_ADAPTER_<SOURCE>_URL` in the DataHub BFF.

Full contract: [ADAPTER_SPEC.md](https://github.com/nkz-os/nkz-module-data-hub/blob/main/ADAPTER_SPEC.md)

---

## License

AGPL-3.0
