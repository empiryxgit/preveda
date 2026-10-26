# PreVeda Madhu-DR - retinal screening node

Diabetic-retinopathy (DR) screening module for a PreVeda hospital node (FRD *6 Madhu*, *4 Hospital Node*, *13 Pattern Store & Model Registry*).
One container image runs a FastAPI service that scores a fundus photo **locally** (ONNX, no cloud calls), returns a triage level with
suggestions taken from a clinician-owned guideline file, stores the result pseudonymised, and keeps a tamper-evident audit log.

> AI-assisted screening aid, **not a diagnosis**. Model stage is `STAGING`: on held-out data AUROC is about 0.80 and it finds roughly
> 70% of DR cases at the review threshold (only 17 DR test images). A "LOW" result does not rule out DR. `config/guidelines.json` is a
> DRAFT until the hospital's ophthalmology lead approves it.

## Layout
```
preveda_dr/
  pyproject.toml  requirements/{base,train,dev}.txt
  config/guidelines.json        clinician-owned follow-up / management / medication text + triage thresholds
  models/registry/<ver>/        dr_model.onnx, reference_embeddings.npz, registry.json (signed)   models/keys/ = PUBLIC key only
  src/preveda_dr/
    core/         settings (env vars), JSON logging
    ml/           preprocessing, inference (ONNX), triage, registry (sha256 + ECDSA)
    persistence/  SQLite/PostgreSQL store, hash-chained audit_log
    security/     JWT (Keycloak/JWKS) + RBAC + node check
    reporting/    printable HTML report
    monitoring/   Prometheus metrics
    api/          main.py (factory), deps.py, routes/{health,predict,results,model,audit,ui}.py
    ingest/       folder scanner: reads images from the configured folder, skips ones already scored
    web/static/   the web app (login, dashboard, results, settings, system) - plain HTML/CSS/JS, works offline
    federated/    PLANNED: head-only Flower client (FRD 7)
    patterns/     PLANNED: Pattern Store (FRD 13)
  training/     prepare_data, preprocess_images, train, export_onnx, build_registry, evaluate
  db/schema.sql PostgreSQL DDL
  tests/{unit,integration}      17 tests
  docs/         architecture, FRD traceability, model card, data dictionary, API, decisions/
  deploy/docker Dockerfile, docker-compose.yml, .env.example   deploy/installer  Windows one-click installer (build_zip.py)   deploy/ci  CI draft
  secrets/      PRIVATE signing key - never committed, never in the image
```

## Run it
**Docker (one container)**
```powershell
docker build -f deploy/docker/Dockerfile -t preveda/madhu-dr:1.0.0 .
docker run -d --name preveda-madhu-dr -p 8080:8080 -v madhu-data:/data preveda/madhu-dr:1.0.0
# or: docker compose -f deploy/docker/docker-compose.yml up -d --build
curl http://localhost:8080/ready      # API;  web app: http://localhost:8081
```
**Without Docker**
```powershell
pip install -r requirements/base.txt -r requirements/dev.txt
$env:PYTHONPATH="src;."; python -m pytest tests -q
python -m preveda_dr.server        # API :8080 + web :8081
# single-port dev alternative: uvicorn --factory preveda_dr.api.main:create_app --port 8080
```
Two ports: **web app** `http://localhost:8081/` and **REST API** `http://localhost:8080/docs` (one container, one process, shared model and database; override with `PREVEDA_API_PORT` / `PREVEDA_WEB_PORT`).
Web app (demo logins `doctor / doctor123` and `admin / admin123`, trial only, active while `PREVEDA_AUTH_MODE=off`).
The interactive API is at `/docs`. In **Settings** an admin sets the image folder; with Docker the chosen host folder is mounted read-only at `/images`.

## API (FRD 6.4 / 9.1 style)
| Endpoint | Role | Purpose |
|---|---|---|
| `POST /madhu/predict/dr` | clinician, hospital_admin | multipart `image` (+ optional `patient_ref` or `abha_hash`, `eye`, `clinical_context` JSON) -> triage, probabilities, suggestions |
| `GET /madhu/dr/results/{id}` | same | stored result (no image bytes) |
| `GET /madhu/dr/report/{id}` | same | printable HTML report with sign-off block |
| `POST /madhu/dr/results/{id}/review` | same | clinician confirms/overrides grade; logged with reviewer + timestamp |
| `GET /madhu/dr/model` | same | version, stage, metrics, signature status |
| `GET /audit/verify` | auditor, hospital_admin | re-computes the audit hash chain |
| `GET /health` `/ready` `/metrics` | open | probes + Prometheus |
```powershell
curl -F "image=@eye.jpg" -F "patient_ref=P-001" -F "eye=Left" http://localhost:8080/madhu/predict/dr
```
With `PREVEDA_AUTH_MODE=hs256|jwks` every call needs `Authorization: Bearer <JWT>` and `X-Hospital-Node: <node id>` (401 / 403 otherwise).

## Model registry and signing
`python -m training.build_registry ...` packages an ONNX model into `models/registry/<version>/`, computes AUROC / sensitivity /
specificity on the held-out split, and signs `registry.json` with `secrets/registry_private.pem`. At start-up the service recomputes the
file hash and verifies the signature with `models/keys/registry_public.pem`; a modified model is refused and `/ready` returns 503.
New models start as `STAGING`; promote to `CANARY`/`PRODUCTION` only after clinical validation.

## Retrain
```powershell
$env:PYTHONPATH="src;."; pip install -r requirements-train.txt
python -m training.prepare_data; python -m training.preprocess_images; python -m training.train; python -m training.export_onnx 1.1.0
```
(`PREVEDA_DATA_DIR` = dataset folder, default = the folder containing this project.) Or build the image with `--build-arg WITH_TRAIN=true`.

## Not built yet (roadmap, in this order)
1. Federated learning: Flower client for the 2,052-value final layer (about 8 KB per round, fits the 11 KB nightly budget), FedProx, Opacus DP (check accuracy at epsilon 0.1).
2. Pattern Store: mine `PAT-DR-xxx` rules from lesion annotations into `pattern_store`.
3. Explainability heat-map (Grad-CAM) on each report; FHIR `DiagnosticReport`/`ImagingStudy` endpoints; MinIO for images.
4. MLflow tracking, Airflow nightly DAG, Evidently drift checks, Helm chart, Keycloak realm, Prometheus dashboards.
5. Per-site labels so the BODH urban/rural fairness gap can be measured.

## Licence
Copyright (c) 2026 Empiryx. All rights reserved. Proprietary software: see [LICENSE](LICENSE). No licence is granted without a signed agreement with Empiryx.
