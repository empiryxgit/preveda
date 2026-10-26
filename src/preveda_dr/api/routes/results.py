"""Stored results, HTML report, clinician review."""
from __future__ import annotations
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from ...persistence import Store
from ...reporting import build_report
from ...security import PREDICT_ROLES, READ_ROLES, Principal, require
from ..deps import get_guidelines, get_store
from fastapi import Request

router = APIRouter(prefix="/madhu/dr", tags=["madhu-dr"])


class ReviewIn(BaseModel):
    confirmed_grade: str
    decision: Literal["accept", "override"]
    rationale: str | None = None


def _load(store: Store, rid: str) -> dict:
    r = store.get_result(rid)
    if not r:
        raise HTTPException(404, "result not found")
    return r


@router.get("/results/{rid}")
def get_result(rid: str, who: Principal = Depends(require(*READ_ROLES)), store: Store = Depends(get_store)):
    r = _load(store, rid)
    r.pop("thumbnail", None)
    for k in ("created_at", "reviewed_at"):
        r[k] = r[k].isoformat() if r.get(k) else None
    return r


@router.get("/report/{rid}", response_class=HTMLResponse)
def report(rid: str, request: Request, who: Principal = Depends(require(*READ_ROLES)),
           store: Store = Depends(get_store), guidelines: dict = Depends(get_guidelines)):
    p = request.app.state.predictor
    return build_report(_load(store, rid), p.bundle.record if p else {}, guidelines)


@router.post("/results/{rid}/review")
def review(rid: str, body: ReviewIn, who: Principal = Depends(require(*PREDICT_ROLES)),
           store: Store = Depends(get_store), guidelines: dict = Depends(get_guidelines)):
    g = guidelines["by_confirmed_grade"]
    if body.confirmed_grade not in g:
        raise HTTPException(422, f"confirmed_grade must be one of {list(g)}")
    _load(store, rid)
    store.review(rid, who.user, body.confirmed_grade, body.decision, body.rationale)
    return {"result_id": rid, "confirmed_grade": body.confirmed_grade, "reviewer": who.user, "plan_for_grade": g[body.confirmed_grade]}
