# Architecture

One container image = one hospital node's DR module. Inference is local (ONNX, CPU); nothing leaves the node.

```
 fundus photo --> POST /madhu/predict/dr
                    |  api/routes/predict.py   (validate, hash patient ref, size limit)
                    v
        ml/preprocessing -> ml/inference (ONNX: logits + 512-d embedding)
                    v
        ml/triage  (probabilities + guidelines.json -> HIGH/MEDIUM/LOW/RETAKE, flags, suggestions)
                    v
        persistence/db  (dr_screening_results + hash-chained audit_log)   monitoring/metrics (Prometheus)
```

## Package map (`src/preveda_dr/`)
| Package | Responsibility | FRD |
|---|---|---|
| `core/` | env settings, JSON logging | 12 |
| `ml/` | preprocessing, ONNX inference, triage rules, signed model registry | 6, 13 |
| `persistence/` | SQLite/Postgres store, audit hash chain | 9, 11 |
| `security/` | JWT (HS256 / JWKS), RBAC, node check | 11 |
| `reporting/` | printable HTML report | 6 |
| `monitoring/` | Prometheus metrics | 12 |
| `ingest/` | folder scanner (Settings path -> results) | 4.3 |
| `web/` | web app served at `/ui` | 6 |
| `api/` | FastAPI factory, deps, routes (health, predict, results, model, audit) | 6.4, 9.1 |
| `federated/` | PLANNED: head-only Flower client, FedProx, DP | 7 |
| `patterns/` | PLANNED: Pattern Store miner / matcher | 13 |

`training/` is offline tooling (needs `requirements/train.txt`); it is not part of the serving import path except `build_registry`, which writes the signed model bundle.

## Model lifecycle
Train -> export ONNX -> `build_registry` writes `models/registry/<ver>/{dr_model.onnx, reference_embeddings.npz, registry.json}` and signs `registry.json` (ECDSA P-256, private key in `secrets/`, never in the image). At start-up the service verifies sha256 + signature; a failing bundle is refused and `/ready` returns 503.

## Terminology
"Pattern" in the training pipeline = per-class embedding centroids + novelty thresholds (`reference_embeddings.npz`). It is distinct from the FRD *Pattern Store*, which is planned under `patterns/`.
