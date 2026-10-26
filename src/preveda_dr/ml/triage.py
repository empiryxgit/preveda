"""Turns model probabilities into a triage level and looks up suggestions in guidelines.json.
The AI never invents treatment advice: every suggestion text comes from the clinician-owned guidelines file."""
from __future__ import annotations
import json
from pathlib import Path

RANK = {"HIGH": 4, "MEDIUM": 3, "RETAKE": 2, "LOW": 1}
DISCLAIMER = ("AI-assisted screening aid - not a diagnosis. Findings and suggestions must be reviewed by a qualified "
              "clinician. No medication should be started or changed from this result.")


def load_guidelines(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def assess(probs: dict[str, float], prediction: str, flags: list[str], guidelines: dict) -> dict:
    th = guidelines["thresholds"]
    p_dr, p_other = probs["DR"], probs["Other"]
    why: list[str] = []
    if p_dr >= th["dr_high"]:
        level, key = "HIGH", "Suspected DR"; why.append(f"P(DR) {p_dr:.0%} >= {th['dr_high']:.0%}")
    elif prediction == "Ungradable":
        level, key = "RETAKE", "Retake"; why.append("image judged ungradable")
    elif p_dr >= th["dr_review"]:
        level, key = "MEDIUM", "Possible DR"; why.append(f"P(DR) {p_dr:.0%} is between {th['dr_review']:.0%} and {th['dr_high']:.0%}")
    elif p_other >= th["other_review"]:
        level, key = "MEDIUM", "Other finding"; why.append(f"P(Other) {p_other:.0%} >= {th['other_review']:.0%}")
    else:
        level, key = "LOW", "No DR suspected"; why.append("no DR signal above threshold")
    escalated = False
    if flags and level == "LOW":
        level, escalated = "MEDIUM", True
        why.append("escalated for manual review: " + ", ".join(flags))
    elif flags:
        why.append("flags: " + ", ".join(flags))
    f = guidelines["findings"][key]
    label = f["label"] + (" - but the AI is unsure, manual review advised" if escalated else "")
    return {"triage": level, "finding_key": key, "ai_finding": label, "why": "; ".join(why),
            "suggested_followup": f["followup"], "suggested_management": f["management"],
            "medication_note": f["medication"], "guidelines_status": guidelines.get("status", "")}
