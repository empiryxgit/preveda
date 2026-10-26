"""POST /madhu/predict/dr  (FRD 6.4)"""
from __future__ import annotations
import hashlib, io, json, re, time, uuid
from typing import Literal
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from ...core.settings import get_settings
from ...ml.inference import InvalidImage, Predictor
from ...ml.triage import DISCLAIMER
from ...monitoring.metrics import LATENCY, PREDICTIONS
from ...persistence import Store
from ...security import PREDICT_ROLES, Principal, require
from ..deps import get_predictor, get_store

router = APIRouter(prefix="/madhu", tags=["madhu-dr"])


@router.post("/predict/dr")
def predict_dr(image: UploadFile = File(...), patient_ref: str | None = Form(None), abha_hash: str | None = Form(None),
               eye: Literal["Left", "Right", "Unknown"] = Form("Unknown"), clinical_context: str | None = Form(None),
               who: Principal = Depends(require(*PREDICT_ROLES)), pred: Predictor = Depends(get_predictor),
               store: Store = Depends(get_store)):
    t0 = time.perf_counter()
    s = get_settings()
    data = image.file.read(s.max_upload_mb * 1024 * 1024 + 1)
    if len(data) > s.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"image larger than {s.max_upload_mb} MB")
    ctx = None
    if clinical_context:
        try:
            ctx = json.loads(clinical_context); assert isinstance(ctx, dict)
        except (ValueError, AssertionError):
            raise HTTPException(400, "clinical_context must be a JSON object")
    if abha_hash and not re.fullmatch(r"[0-9a-fA-F]{64}", abha_hash):
        raise HTTPException(400, "abha_hash must be a 64-character SHA-256 hex string")
    phash = abha_hash.lower() if abha_hash else (
        hashlib.sha256((s.hash_salt + patient_ref).encode()).hexdigest() if patient_ref else None)
    try:
        res, pre = pred.predict_bytes(data)
    except InvalidImage as e:
        raise HTTPException(400, str(e))
    thumb = None
    if s.store_thumbnails:
        b = io.BytesIO(); pre.resize((300, 300)).save(b, "JPEG", quality=85); thumb = b.getvalue()
    rid, ms = str(uuid.uuid4()), (time.perf_counter() - t0) * 1000
    bundle = pred.bundle
    store.insert_result(dict(
        result_id=rid, hospital_node_id=s.hospital_node_id, patient_hash=phash, eye=eye,
        image_sha256=hashlib.sha256(data).hexdigest(), model_version=bundle.version, model_stage=bundle.record.get("stage"),
        prediction=res["prediction"], confidence=res["confidence"], probabilities=res["probabilities"], flags=res["flags"],
        triage=res["triage"], ai_finding=res["ai_finding"], rationale=res["why"], clinical_context=ctx,
        thumbnail=thumb, latency_ms=ms), actor=who.user)
    PREDICTIONS.labels(res["triage"], bundle.version).inc(); LATENCY.observe(ms / 1000)
    return {"result_id": rid, "triage": res["triage"], "ai_finding": res["ai_finding"], "rationale": res["why"],
            "prediction": res["prediction"], "confidence": round(res["confidence"], 4),
            "probabilities": {k: round(v, 4) for k, v in res["probabilities"].items()}, "flags": res["flags"],
            "suggested_followup": res["suggested_followup"], "suggested_management": res["suggested_management"],
            "medication_note": res["medication_note"], "guidelines_status": res["guidelines_status"],
            "model": {"name": bundle.record["model_name"], "version": bundle.version, "stage": bundle.record.get("stage"),
                      "signature_verified": bundle.signature_verified},
            "latency_ms": round(ms, 1), "report_url": f"/madhu/dr/report/{rid}", "disclaimer": DISCLAIMER}
