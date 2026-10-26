# Madhu-DR Developer Guide

One file to understand the project: structure, how data is read, what is stored, and where.
Status: model 1.0.0 is `STAGING`. This is a screening aid, not a diagnosis.

---
## 1. Two separate worlds

| | **Training (offline, once per model version)** | **Serving (online, every request)** |
|---|---|---|
| Code | `training/` | `src/preveda_dr/` |
| Needs | PyTorch (`requirements/train.txt`) | ONNX Runtime only (`requirements/base.txt`) |
| Input | Fundus images + CSV labels | One uploaded fundus image |
| Output | Signed model bundle in `models/registry/<ver>/` | A triage result row + HTML report |
| Runs in | Developer machine (CPU) | The container image |

The only thing that crosses from training to serving is the **signed model bundle**.

---
## 2. Folder structure

```
preveda_dr/
  pyproject.toml, requirements/{base,train,dev}.txt
  config/guidelines.json      clinician-owned thresholds + follow-up/management text (DRAFT)
  models/
    registry/<ver>/           dr_model.onnx, reference_embeddings.npz, registry.json (signed)
    registry/CURRENT          text file: the active version
    keys/registry_public.pem  PUBLIC key (ships in the image)
  secrets/registry_private.pem  PRIVATE signing key. Never commit. Never in the image.
  db/schema.sql               PostgreSQL DDL
  src/preveda_dr/
    core/         settings.py (env vars), logging.py (JSON logs)
    ml/           preprocessing, inference, triage, registry
    persistence/  db.py (Store: results + audit log)
    security/     auth.py (JWT, roles, node check)
    reporting/    html_report.py
    monitoring/   metrics.py (Prometheus)
    api/          main.py (app factory), deps.py, routes/{health,predict,results,model,audit,ui}.py
    ingest/       folder_scanner.py (reads the configured folder, scores new images)
    web/static/   index.html, app.css, app.js (the web app, no external libraries)
    federated/    PLANNED (Flower client, head-only)
    patterns/     PLANNED (Pattern Store)
  training/       prepare_data, preprocess_images, train, export_onnx, build_registry, evaluate
  tests/{unit,integration}
  docs/           architecture, model card, data dictionary, FRD traceability, decisions/
  deploy/         docker/ (Dockerfile, compose), ci/
```

Rule of thumb: routes are thin; logic lives in `ml/`, `persistence/`, `security/`, `reporting/`.

---
## 3. Training flow: how data is READ

Environment variables (`training/settings.py`): `PREVEDA_DATA_DIR` (dataset), `PREVEDA_WORK_DIR` (intermediate files), `PREVEDA_TRAIN_MODEL_DIR` (output). Also `TRAIN_MODE`, `EPOCHS`, `BATCH_SIZE`.

1. **prepare_data.py** reads the dataset folder: images plus the label CSV.
   - Key point: the CSV `Combined ID` is wrong for about 554 of 921 images. We use **`combined_id` = image filename stem** and keep the original as `csv_combined_id`.
   - Patient is parsed from the filename (`^(\d+)_(?:(LE|RE)_)?`); unlabeled images become "Image n".
   - Writes `labels.csv` and `split.csv` (patient-level StratifiedGroupKFold, about 64/16/20, so one patient never spans train and test).
2. **preprocess_images.py** crops the black border (threshold 12), pads to square, resizes to 320x320, caches to `images_320/`. Same code as serving (`ml/preprocessing.py`), so train and serve see identical pixels.
3. **train.py** fine-tunes ResNet-18 (ImageNet) to 4 classes: Ungradable / Healthy / DR / Other. Class-weighted loss, label smoothing 0.05, AdamW, cosine LR, early stopping on validation macro-F1. Writes `best.pt`, `metrics.json`.
4. **export_onnx.py** exports `dr_model.onnx` (outputs `logits` and a 512-d `embedding`) and builds the reference **pattern**: per-class centroid of L2-normalised embeddings plus 95th-percentile cosine-distance novelty thresholds, saved as `reference_embeddings.npz`.
5. **build_registry.py** copies these into `models/registry/<ver>/`, computes sha256, writes `registry.json` (stage, classes, metrics), and signs it with the private key (ECDSA P-256).

Where training files land:

| File | Location |
|---|---|
| labels.csv, split.csv, images_320/, metrics.json, best.pt | `PREVEDA_WORK_DIR` |
| dr_model.onnx, reference_embeddings.npz, pattern.json | `PREVEDA_TRAIN_MODEL_DIR` |
| Final signed bundle | `models/registry/<ver>/` |

---
## 4. Serving flow: what happens on one request

`POST /madhu/predict/dr` (multipart: `image`, optional `patient_ref` or `abha_hash`, `eye`, `clinical_context` JSON)

1. **Auth** (`security/auth.py`): if `PREVEDA_AUTH_MODE` is `hs256` or `jwks`, needs a Bearer JWT with a clinician/hospital_admin role plus `X-Hospital-Node`. Mode `off` is for dev only.
2. **Validate**: size limit (`PREVEDA_MAX_UPLOAD_MB`), `abha_hash` must be 64 hex chars, `clinical_context` must be a JSON object.
3. **Pseudonymise**: raw patient ID is never stored. `patient_hash` = given `abha_hash`, or SHA-256(`PREVEDA_PATIENT_HASH_SALT` + `patient_ref`).
4. **Preprocess** (`ml/preprocessing.py`) then **infer** (`ml/inference.py`, ONNX CPU) giving probabilities and the embedding. The embedding is compared with the reference pattern to flag "unlike training data".
5. **Triage** (`ml/triage.py`) applies thresholds from `config/guidelines.json` (dr_high 0.40, dr_review 0.15, other_review 0.40) and returns HIGH / MEDIUM / LOW / RETAKE, flags, and suggested follow-up/management text. The model does **not** predict severity grade; grade only comes from clinician review.
6. **Persist** (`persistence/db.py`): one row in `dr_screening_results` and one chained row in `audit_log`.
7. **Respond** with triage, probabilities, flags, suggestions, model version/stage/signature status, report URL, disclaimer. Prometheus counters and latency updated.

Later calls: `GET /madhu/dr/results/{id}`, `GET /madhu/dr/report/{id}` (HTML), `POST /madhu/dr/results/{id}/review` (clinician confirms/overrides grade), `GET /madhu/dr/model`, `GET /audit/verify`, plus `/health`, `/ready`, `/metrics`.

---
## 4b. Web app and folder ingestion
- **Two listeners, one process** (`server.py`, `api/main.py:create_pair`): REST API on `PREVEDA_API_PORT` (8080: `/docs`, `/madhu/*`, `/health`, `/ready`, `/metrics`, `/audit/verify`) and the web app on `PREVEDA_WEB_PORT` (8081: `/ui`, `/ui-api/*`). They share one model, database and scanner. Host-side ports are set in compose (`.env`); the Windows installer picks free ones.
- **Web app** (`/ui`, source in `web/static/`) talks to `/ui-api/*` (`api/routes/ui.py`). Screens: Login, Dashboard, Results (+ detail drawer with doctor review), Settings, System.
- **Dummy login** (`security/demo.py`): users from `PREVEDA_DEMO_USERS` (default `doctor/doctor123` = clinician, `admin/admin123` = hospital_admin), in-memory sessions, 5 failed tries then a 5-minute lock. Honoured ONLY while `PREVEDA_AUTH_MODE=off`; with hs256/jwks the login endpoint returns 404. Replace with Keycloak for real use.
- **Folder path setting:** an admin sets it in Settings; stored in table `app_settings` (`watch_path`, `auto_scan`, `scan_interval`), every change goes to the audit log. Default = `PREVEDA_IMAGES_DIR` (`/images`).
- **Docker:** the host folder chosen at install time is bind-mounted read-only to `/images` (compose var `PREVEDA_HOST_IMAGES_DIR`). A Windows path typed in Settings is rejected with an explanation, because the service sees the container's filesystem.
- **Scanner** (`ingest/folder_scanner.py`): walks the folder, accepts jpg/png/tif/bmp, skips files already scored (by SHA-256), scores new ones, stores the result with `clinical_context = {source: "folder", source_file, combined_id}` (combined_id = filename stem, see ADR 0001). Runs on "Scan now" or automatically every `scan_interval` seconds when auto-scan is on.

---
## 5. What is stored, and where

| Data | Where | Notes |
|---|---|---|
| Screening results | table `dr_screening_results` | patient_hash, eye, image_sha256, model_version/stage, prediction, confidence, probabilities, flags, triage, ai_finding, rationale, clinical_context, optional 300px thumbnail, latency_ms, review fields |
| UI settings | table `app_settings` | folder path, auto-scan, interval |
| Audit log | table `audit_log` | append-only; each row hashes the previous (genesis = 64 zeros); `/audit/verify` recomputes the chain and reports edits/deletions |
| **The uploaded image** | **Not stored.** Only its SHA-256, plus an optional small thumbnail (`PREVEDA_STORE_THUMBNAILS`) | |
| Raw patient ID | **Never stored** | only the salted hash |
| Database | `PREVEDA_DATABASE_URL`: SQLite `sqlite:////data/madhu_dr.db` (container default, volume `/data`), or PostgreSQL (`db/schema.sql`) | |
| Model + pattern | `PREVEDA_MODELS_DIR` (container: `/models`), version in `registry/CURRENT` | loaded once at start-up |
| Guidelines | `PREVEDA_GUIDELINES` (container: `/app/config/guidelines.json`) | edit here, not in code |
| Signing keys | public in `models/keys/`; private only in `secrets/` | |

Model integrity: at start-up `ml/registry.py` checks the ONNX sha256 and the ECDSA signature. If either fails the model is **refused**, the service stays up, and `/ready` returns 503 with the reason.

---
## 6. Configuration (environment variables)

`PREVEDA_MODELS_DIR`, `_MODEL_VERSION`, `_DATABASE_URL`, `_HOSPITAL_NODE_ID`, `_AUTH_MODE` (off|hs256|jwks), `_JWT_SECRET`, `_JWKS_URL`, `_JWT_AUDIENCE`, `_REQUIRE_SIGNATURE`, `_GUIDELINES`, `_MAX_UPLOAD_MB`, `_PATIENT_HASH_SALT` (change per hospital), `_STORE_THUMBNAILS`, `_ORT_THREADS`, `_DEMO_LOGIN`, `_DEMO_USERS`, `_IMAGES_DIR`, `_SESSION_HOURS`. Defaults are in `core/settings.py`.

---
## 7. Run, test, extend

```powershell
pip install -r requirements/base.txt -r requirements/dev.txt
$env:PYTHONPATH="src;."; python -m pytest tests -q          # 17 tests
uvicorn --factory preveda_dr.api.main:create_app --port 8080  # docs at /docs
```
- **New endpoint:** add `api/routes/<name>.py`, register the router in `api/main.py`, take dependencies from `api/deps.py`.
- **Change triage wording/thresholds:** edit `config/guidelines.json` only (clinician sign-off needed).
- **New model version:** run training steps 1-5 with a new `--version`, then set `PREVEDA_MODEL_VERSION` or `registry/CURRENT`. Never edit `registry.json` by hand (signature will fail).
- **Container:** `docker build -f deploy/docker/Dockerfile -t preveda/madhu-dr:1.0.0 .` (image has the public key and models, never the private key).

---
## 8. Known limits (keep in every report)
- Held-out AUROC about 0.80; DR sensitivity 47% at argmax, about 71% at the review threshold (0.15) with 78% specificity; only 17 DR test images. A LOW result does not rule out DR.
- No per-site labels, so fairness across hospitals is unassessed.
- Guideline text is a DRAFT until the ophthalmology lead approves it.
- Roadmap (not built): federated head-only training (final layer = 2,052 floats, about 8 KB), Pattern Store, Grad-CAM, FHIR DiagnosticReport, MLflow/Airflow/Evidently, Helm, Keycloak.
