"""Endpoints that feed the built-in web app (/ui). Protected by the demo login (see security/demo.py)."""
from __future__ import annotations
from datetime import date, timedelta
from typing import Literal
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from ... import __version__
from ...core.settings import get_settings
from ...ingest import validate_path
from ...ingest.folder_scanner import config as scan_config
from ...ml.triage import DISCLAIMER, assess
from ...reporting import build_report
from ...security import demo
from ..deps import get_guidelines, get_store

router = APIRouter(prefix="/ui-api", tags=["web-ui"])
anyone = demo.current()
workers = demo.current(*demo.WORK_ROLES)
admins = demo.current(*demo.ADMIN_ROLES)


class LoginIn(BaseModel):
    username: str
    password: str


class SettingsIn(BaseModel):
    watch_path: str
    auto_scan: bool
    scan_interval: int


class PathIn(BaseModel):
    path: str


class ReviewIn(BaseModel):
    confirmed_grade: str
    decision: Literal["accept", "override"]
    rationale: str | None = None


def _row(r: dict) -> dict:
    ctx = r.get("clinical_context") or {}
    return {"result_id": r["result_id"], "created_at": r["created_at"].isoformat(), "record": ctx.get("combined_id") or r["result_id"][:8],
            "source_file": ctx.get("source_file"), "source": ctx.get("source", "api"), "eye": r["eye"], "triage": r["triage"],
            "prediction": r["prediction"], "confidence": round(r["confidence"] or 0, 3), "flags": r["flags"] or [],
            "reviewed": r["reviewed_at"] is not None, "confirmed_grade": r["confirmed_grade"]}


def _model(request: Request) -> dict:
    p = request.app.state.predictor
    if p is None:
        return {"loaded": False, "error": request.app.state.model_error}
    b, r = p.bundle, p.bundle.record
    return {"loaded": True, "name": r["model_name"], "version": b.version, "stage": r.get("stage"), "classes": r["classes"],
            "created": r.get("created"), "metrics": r.get("accuracy_metrics"), "signature_verified": b.signature_verified,
            "onnx_sha256": r["artefact"]["sha256"]}


@router.post("/login")
def login(body: LoginIn):
    tok, s = demo.login(body.username, body.password)
    return {"token": tok, "user": {"username": s.user, "name": s.name, "role": s.role}}


@router.post("/logout")
def logout(authorization: str | None = Header(None)):
    demo.logout(authorization)
    return {"ok": True}


@router.get("/me")
def me(s=Depends(anyone)):
    return {"username": s.user, "name": s.name, "role": s.role, "node": get_settings().hospital_node_id, "version": __version__}


@router.get("/dashboard")
def dashboard(request: Request, s=Depends(anyone), store=Depends(get_store)):
    st = store.stats()
    today = date.today()
    days = [(today - timedelta(days=i)).isoformat() for i in range(13, -1, -1)]
    rows, _ = store.list_results(limit=8)
    attention, _ = store.list_results(limit=200)
    need = [_row(r) for r in attention if r["triage"] in ("HIGH", "MEDIUM") and r["reviewed_at"] is None][:6]
    return {"totals": st, "trend": [{"day": d, "count": st["per_day"].get(d, 0)} for d in days], "recent": [_row(r) for r in rows],
            "needs_attention": need, "model": _model(request), "scan": request.app.state.scanner.status(),
            "config": scan_config(store), "audit": store.verify_audit()}


@router.get("/results")
def results(triage: str | None = None, q: str | None = None, limit: int = 15, offset: int = 0, s=Depends(anyone), store=Depends(get_store)):
    rows, total = store.list_results(triage if triage in ("HIGH", "MEDIUM", "LOW", "RETAKE") else None, (q or "").strip() or None,
                                     max(1, min(limit, 100)), max(0, offset))
    return {"items": [_row(r) for r in rows], "total": total}


def _load(store, rid: str) -> dict:
    r = store.get_result(rid)
    if not r:
        raise HTTPException(404, "result not found")
    return r


@router.get("/results/{rid}")
def result_detail(rid: str, request: Request, s=Depends(anyone), store=Depends(get_store), g: dict = Depends(get_guidelines)):
    r = _load(store, rid)
    a = assess(r["probabilities"], r["prediction"], r["flags"] or [], g)
    return {**_row(r), "probabilities": r["probabilities"], "ai_finding": r["ai_finding"], "rationale": r["rationale"],
            "model_version": r["model_version"], "model_stage": r["model_stage"], "has_thumbnail": r["thumbnail"] is not None,
            "suggested_followup": a["suggested_followup"], "suggested_management": a["suggested_management"],
            "medication_note": a["medication_note"], "guidelines_status": a["guidelines_status"], "disclaimer": DISCLAIMER,
            "grades": list(g["by_confirmed_grade"]), "review": {"reviewer": r["reviewer_id"], "grade": r["confirmed_grade"],
            "decision": r["review_decision"], "rationale": r["review_rationale"],
            "at": r["reviewed_at"].isoformat() if r["reviewed_at"] else None}}


@router.get("/results/{rid}/thumbnail")
def thumbnail(rid: str, s=Depends(anyone), store=Depends(get_store)):
    r = _load(store, rid)
    if not r["thumbnail"]:
        raise HTTPException(404, "no thumbnail stored")
    return Response(r["thumbnail"], media_type="image/jpeg")


@router.get("/results/{rid}/report", response_class=HTMLResponse)
def report(rid: str, request: Request, s=Depends(anyone), store=Depends(get_store), g: dict = Depends(get_guidelines)):
    p = request.app.state.predictor
    return build_report(_load(store, rid), p.bundle.record if p else {}, g)


@router.post("/results/{rid}/review")
def review(rid: str, body: ReviewIn, s=Depends(workers), store=Depends(get_store), g: dict = Depends(get_guidelines)):
    if body.confirmed_grade not in g["by_confirmed_grade"]:
        raise HTTPException(422, f"confirmed_grade must be one of {list(g['by_confirmed_grade'])}")
    _load(store, rid)
    store.review(rid, s.user, body.confirmed_grade, body.decision, body.rationale)
    return {"ok": True}


@router.get("/settings")
def get_cfg(s=Depends(anyone), store=Depends(get_store)):
    return {**scan_config(store), "default_path": get_settings().images_dir, "can_edit": s.role in demo.ADMIN_ROLES}


@router.put("/settings")
def put_cfg(body: SettingsIn, s=Depends(admins), store=Depends(get_store)):
    store.set_setting("watch_path", body.watch_path.strip(), s.user)
    store.set_setting("auto_scan", "true" if body.auto_scan else "false", s.user)
    store.set_setting("scan_interval", str(max(10, min(body.scan_interval, 86400))), s.user)
    return scan_config(store)


@router.post("/settings/test-path")
def test_path(body: PathIn, s=Depends(anyone)):
    return validate_path(body.path)


@router.post("/scan")
def scan(request: Request, s=Depends(workers)):
    started = request.app.state.scanner.start(s.user)
    return {"started": started, "status": request.app.state.scanner.status()}


@router.get("/scan/status")
def scan_status(request: Request, s=Depends(anyone)):
    return request.app.state.scanner.status()


@router.get("/system")
def system(request: Request, s=Depends(anyone), store=Depends(get_store)):
    return {"model": _model(request), "audit": store.verify_audit(), "audit_tail": store.audit_tail(15),
            "node": get_settings().hospital_node_id, "version": __version__, "auth_mode": get_settings().auth_mode,
            "api_url": get_settings().public_api_url or f"http://localhost:{get_settings().api_port}"}
