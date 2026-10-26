# FRD v1.0.0 traceability

| FRD item | Status | Where |
|---|---|---|
| Offline-first ONNX inference on CPU | Done | `ml/inference.py` |
| `POST /madhu/predict/dr` | Done | `api/routes/predict.py` |
| Signed Model Registry, stages, integrity check (AC-FL4) | Done (STAGING) | `ml/registry.py`, `training/build_registry.py` |
| Hash-chained audit log | Done | `persistence/db.py`, `/audit/verify` |
| Keycloak JWT RBAC, node header | Done (HS256/JWKS) | `security/auth.py` |
| Prometheus metrics, health/ready | Done | `monitoring/`, `api/routes/health.py` |
| Pseudonymised patient reference (ABHA hash) | Done | `routes/predict.py` |
| PostgreSQL schema | Done | `db/schema.sql` |
| One container image | Dockerfile drafted, build pending | `deploy/docker/` |
| Federated learning (Flower, FedAvg/FedProx mu=0.01) | Planned | `federated/` |
| Differential privacy (Opacus, eps=0.1) | Planned | `federated/` |
| Pattern Store | Planned | `patterns/` |
| FHIR R4 DiagnosticReport / ABHA | Planned | - |
| Grad-CAM explanations | Planned | - |
| MLflow / Airflow / Evidently, Helm/K8s | Planned | `deploy/` |
