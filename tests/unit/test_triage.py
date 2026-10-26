from preveda_dr.ml.triage import assess, load_guidelines
from pathlib import Path

G = load_guidelines(Path(__file__).resolve().parents[2] / "config" / "guidelines.json")


def p(dr=0.0, h=0.0, o=0.0, u=0.0):
    return {"DR": dr, "Healthy": h, "Other": o, "Ungradable": u}


def test_high_when_dr_probability_high():
    r = assess(p(dr=0.6, o=0.4), "DR", [], G)
    assert r["triage"] == "HIGH" and r["finding_key"] == "Suspected DR"


def test_medium_in_review_band():
    assert assess(p(dr=0.25, h=0.7), "Healthy", [], G)["triage"] == "MEDIUM"


def test_retake_for_ungradable():
    assert assess(p(u=0.9, h=0.1), "Ungradable", [], G)["triage"] == "RETAKE"


def test_low_and_escalation_by_flag():
    assert assess(p(h=0.95, dr=0.02), "Healthy", [], G)["triage"] == "LOW"
    r = assess(p(h=0.5, dr=0.05), "Healthy", ["low_confidence"], G)
    assert r["triage"] == "MEDIUM" and "unsure" in r["ai_finding"]


def test_suggestions_come_from_guidelines_file():
    r = assess(p(dr=0.6), "DR", [], G)
    assert r["suggested_followup"] == G["findings"]["Suspected DR"]["followup"]
    assert r["guidelines_status"].startswith("DRAFT")
