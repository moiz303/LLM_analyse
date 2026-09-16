# Interactive Model Compression Backend

Backend and local observability stack for the interactive model-compression demo.
The expensive black-box experiment runs offline. The API uses its result as a
baseline and answers slider changes through an explainable sensitivity predictor.

## Architecture

```text
comparison.json (source of truth)
        ├── FastAPI validation / model configuration
        ├── data/model.json (user buffer)
        ├── data/experiments/*.json (history)
        └── ingest.py ──> InfluxDB ──> Grafana

Frontend ──POST /api/predict──> FastAPI ──> InfluxDB
```

The three data tiers are intentionally separate:

* `comparison.json` is never changed automatically and is used by Reset to
  baseline.
* `data/model.json` is the current slider buffer. It is initialized from the
  source file and updated after successful predictions.
* `data/experiments/` contains validated experiment snapshots. They are used
  for support-distance calculations and history.

If the source file is unavailable, the backend falls back to
`data/model.json`, then to the newest file in `data/experiments/`. The source
file is always preferred when it exists.

## Quick start

Requirements: Docker with Compose and Python 3.11+ for running `ingest.py`
locally.

```bash
cp .env.example .env
```

Fill in local-only values in `.env`:

* `INFLUXDB_PASSWORD` and `INFLUXDB_TOKEN` initialize InfluxDB.
* `GRAFANA_ADMIN_PASSWORD` sets the Grafana admin password.
* `BACKEND_PORT`, `INFLUXDB_PORT`, and `GRAFANA_PORT` are host-facing ports.
* `*_CONTAINER_PORT` and `INFLUXDB_URL` are internal Docker connection settings.
* Keep `INFLUXDB_ORG=mlops`, `INFLUXDB_BUCKET=model_comparison`, and
  `INFLUXDB_RETENTION=365d` unless the frontend has a different contract.
* `FRONTEND_ORIGINS` should contain only the frontend origins, such as
  `http://localhost:5173`.

Start all services:

```bash
docker compose up -d --build
```

The services are on one Docker network and are available at:

* Backend: `http://localhost:8000`
* InfluxDB: `http://localhost:8086`
* Grafana: `http://localhost:3000`
* Dashboard iframe:
  `http://localhost:3000/d/model-comparison/model-comparison?orgId=1&kiosk`

The frontend can use:

```env
VITE_GRAFANA_DASHBOARD_URL=http://localhost:3000/d/model-comparison/model-comparison?orgId=1&kiosk
```

Load the actual black-box result once after InfluxDB is ready:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements.txt
python backend/ingest.py comparison.json
```

The script validates the canonical experiment contract before writing anything.
Invalid data is neither stored as an experiment nor written to InfluxDB.

## API

### `GET /health`

Returns `{ "status": "ok" }`.

### `GET /api/model`

Returns model ID, current configuration, slider UI ranges, physical valid
ranges, critical flags, sensitivity data, baseline metrics, metric direction,
and constraints. The frontend does not need to hardcode model parameters.

### `POST /api/predict`

Request:

```json
{
  "parameters": {
    "param_a": 0.76,
    "param_b": 0.47,
    "param_c": 1.15
  }
}
```

The backend validates the complete configuration, predicts quality/resource
metrics, clamps predictions to physical constraints, calculates support from
the nearest known experiment, updates `data/model.json`, and writes a
`result_type=predicted` record to InfluxDB. `support` is an extrapolation
indicator, not a probability of correctness.

### `POST /api/reset`

Always reads the source `comparison.json`, restores `data/model.json`, and
predicts the source configuration. The returned prediction is anchored exactly
to the compressed metrics from the source experiment.

### `GET /api/experiments`

Lists validated experiment snapshots. `GET /api/experiments/{experiment_id}`
returns one snapshot. `POST /api/experiments` validates and stores a canonical
experiment and ingests its actual compressed metrics.

## Actual vs predicted semantics

Actual points are produced by `ingest.py` or the experiment ingestion endpoint:

* `result_type=actual`
* `prediction_mode=black_box`
* value is the measured compressed result from the black-box experiment

Interactive API calls produce separate points:

* `result_type=predicted`
* `prediction_mode=sensitivity_model`
* value is calculated by the backend surrogate

The frontend never connects to InfluxDB directly. Grafana and the backend use
the internal address from `INFLUXDB_URL`; a browser uses the host-facing port
from `INFLUXDB_PORT` or `GRAFANA_PORT`.

## Tests

```bash
pytest -q backend/tests
```

The tests cover experiment validation, missing/invalid fields, baseline
anchoring, sensitivity changes, physical constraints, API errors, reset
behavior, and persistence through the application service boundary.

The full Docker/InfluxDB/Grafana pipeline has a separate integration
smoke-check. It starts an isolated Compose project with temporary credentials
and host ports, then verifies actual and predicted InfluxDB points, the Grafana
datasource, and the provisioned dashboard:

```bash
pnpm test:compose
```

The check requires a running Docker daemon and exits non-zero on any service,
API, persistence, or provisioning failure. It removes the temporary Compose
containers, volumes, and network when it finishes.

## Configuration and provisioning

* `Dockerfile` builds the FastAPI service.
* `docker-compose.yml` starts backend, InfluxDB 2.7, and Grafana 11.
* `provisioning/datasources/influxdb.yml` creates the Flux datasource from
  environment variables.
* `provisioning/dashboards/dashboard.yml` loads the supplied dashboard provider.
* `provisioning/dashboards/model_comparison.json` shows actual, predicted,
  baseline, support, resource metrics, and history.

Credentials are read from `.env`, which is ignored by Git. Never commit the
local token or passwords.