from __future__ import annotations
from fastapi import APIRouter, Depends
from ...ml.inference import Predictor
from ...security import READ_ROLES, Principal, require
from ..deps import get_predictor

router = APIRouter(prefix="/madhu/dr", tags=["madhu-dr"])


@router.get("/model")
def model_info(who: Principal = Depends(require(*READ_ROLES)), pred: Predictor = Depends(get_predictor)):
    b = pred.bundle; r = b.record
    return {"model_name": r["model_name"], "version": b.version, "stage": r.get("stage"), "aggregation": r.get("aggregation"),
            "classes": r["classes"], "created": r.get("created"), "accuracy_metrics": r.get("accuracy_metrics"),
            "training": r.get("training"), "signature_verified": b.signature_verified, "onnx_sha256": r["artefact"]["sha256"]}
