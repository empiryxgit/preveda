# API

Interactive docs at `/docs`. Auth: `PREVEDA_AUTH_MODE=off|hs256|jwks`; when on, send `Authorization: Bearer <JWT>` and `X-Hospital-Node`. Roles: clinician and hospital_admin predict/read/review; auditor and hospital_admin verify audit.

See README for the endpoint table. Responses always carry `disclaimer`, `model.version/stage/signature_verified`, and `guidelines_status`.
