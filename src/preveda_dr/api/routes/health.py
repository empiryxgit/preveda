from __future__ import annotations
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from ... import __version__

router = APIRouter(tags=["ops"])


@router.get("/health")
def health():
    return {"status": "ok", "version": __version__}


@router.get("/ready")
def ready(request: Request):
    p, err = request.app.state.predictor, request.app.state.model_error
    try:
        request.app.state.store.ping(); db = True
    except Exception:
        db = False
    ok = p is not None and db
    return JSONResponse({"ready": ok, "model_loaded": p is not None, "model_error": err, "database": db,
                         "model_version": p.bundle.version if p else None}, status_code=200 if ok else 503)


@router.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
