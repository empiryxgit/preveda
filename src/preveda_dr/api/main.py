"""Application factories.
  create_app()        everything on one app (tests, `uvicorn --factory preveda_dr.api.main:create_app`)
  create_pair()       (api_app, web_app) sharing ONE model/database/scanner - used by `python -m preveda_dr.server`
                      to expose the REST API on one port and the web app on another."""
from __future__ import annotations
import time, uuid
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import State
from .. import __version__
from ..core.logging import log_event, setup_logging
from ..core.settings import get_settings
from ..ingest import FolderScanner
from ..ml.inference import Predictor
from ..ml.registry import ModelIntegrityError, load_bundle
from ..ml.triage import load_guidelines
from ..persistence import Store
from .routes import audit, health, model, predict, results, ui

STATIC = Path(__file__).resolve().parents[1] / "web" / "static"
API_ROUTERS = (health.router, predict.router, results.router, model.router, audit.router)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    s = get_settings()
    setup_logging()
    if s.auth_mode == "hs256" and not s.jwt_secret:
        raise RuntimeError("PREVEDA_AUTH_MODE=hs256 needs PREVEDA_JWT_SECRET")
    if s.auth_mode == "jwks" and not s.jwks_url:
        raise RuntimeError("PREVEDA_AUTH_MODE=jwks needs PREVEDA_JWKS_URL")
    app.state.guidelines = load_guidelines(s.guidelines_path)
    app.state.store = Store(s.database_url)
    app.state.predictor, app.state.model_error = None, None
    try:    # a model that fails verification is refused; the node stays up but reports not-ready (AC-FL4)
        b = load_bundle(s.models_dir, s.model_version, s.require_signature)
        app.state.predictor = Predictor(b, app.state.guidelines, s.ort_threads)
        log_event("model loaded", version=b.version, stage=b.record.get("stage"), signature_verified=b.signature_verified)
    except (ModelIntegrityError, FileNotFoundError) as e:
        app.state.model_error = str(e)
        log_event("model REFUSED", reason=str(e))
    app.state.scanner = FolderScanner(app)
    app.state.scanner.start_auto_loop()
    yield
    app.state.scanner.stop()


def _add_context(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_context(request: Request, call_next):
        rid, t0 = request.headers.get("X-Request-ID") or str(uuid.uuid4()), time.perf_counter()
        if not hasattr(request.app.state, "store"):       # the other listener's start-up has not finished yet
            return JSONResponse({"detail": "service is starting, retry in a few seconds"}, status_code=503)
        resp = await call_next(request)
        resp.headers["X-Request-ID"] = rid
        resp.headers["X-Hospital-Node"] = get_settings().hospital_node_id
        log_event("request", request_id=rid, method=request.method, path=request.url.path, status=resp.status_code,
                  ms=round((time.perf_counter() - t0) * 1000, 1))
        return resp


def _mount_web(app: FastAPI) -> None:
    app.include_router(ui.router)
    app.mount("/ui", StaticFiles(directory=STATIC, html=True), name="ui")

    @app.get("/", include_in_schema=False)
    def root():
        return RedirectResponse("/ui/")


def create_app() -> FastAPI:
    app = FastAPI(title="PreVeda Madhu-DR", version=__version__, lifespan=_lifespan)
    _add_context(app)
    for r in API_ROUTERS:
        app.include_router(r)
    _mount_web(app)
    return app


def create_pair() -> tuple[FastAPI, FastAPI]:
    shared = State()
    api = FastAPI(title="PreVeda Madhu-DR API", version=__version__, lifespan=_lifespan)
    api.state = shared
    _add_context(api)
    for r in API_ROUTERS:
        api.include_router(r)

    @api.get("/", include_in_schema=False)
    def api_root():
        return {"service": "PreVeda Madhu-DR API", "version": __version__, "docs": "/docs", "health": "/health"}

    web = FastAPI(title="PreVeda Madhu-DR Web", version=__version__, docs_url=None, redoc_url=None, openapi_url=None)
    web.state = shared
    _add_context(web)

    @web.get("/health", include_in_schema=False)
    def web_health():
        return {"status": "ok", "version": __version__}

    _mount_web(web)
    return api, web
