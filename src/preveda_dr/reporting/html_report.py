"""One-page HTML report for a single screening result."""
from __future__ import annotations
import base64, html
from ..ml.triage import DISCLAIMER

E = html.escape
CSS = """body{font-family:Segoe UI,Arial,sans-serif;margin:0;background:#f4f5f7;color:#1c1f24}.w{max-width:900px;margin:0 auto;padding:20px}
h1{font-size:21px;margin:0 0 4px}h2{font-size:16px;margin:20px 0 8px}.warn{background:#fff4e5;border:1px solid #f0b35a;padding:10px 14px;border-radius:8px;font-size:13px}
.card{background:#fff;border-radius:10px;padding:14px;margin:10px 0;box-shadow:0 1px 3px #0001}.card img{width:170px;height:170px;border-radius:8px;float:left;margin-right:14px;background:#000}
.badge{display:inline-block;padding:2px 10px;border-radius:12px;font-weight:600;font-size:12px;color:#fff}.HIGH{background:#c62828}.MEDIUM{background:#ef8a00}.LOW{background:#2e7d32}.RETAKE{background:#546e7a}
table{border-collapse:collapse;width:100%;font-size:13px}td,th{border-bottom:1px solid #e3e6ea;padding:5px 8px;text-align:left;vertical-align:top}th{background:#f0f2f5;width:30%}
.bar{background:#e3e6ea;border-radius:4px;height:8px;width:140px;display:inline-block;vertical-align:middle}.bar i{display:block;height:8px;border-radius:4px;background:#3b6fd4}.small{font-size:12px;color:#5b6570}"""


def build_report(r: dict, record: dict, guidelines: dict) -> str:
    probs = r["probabilities"]
    bars = "".join(f"<div class='small'>{E(c):<11}<span class='bar'><i style='width:{v*100:.0f}%'></i></span> {v:.0%}</div>" for c, v in probs.items())
    img = ("<img src='data:image/jpeg;base64," + base64.b64encode(r["thumbnail"]).decode() + "'>") if r.get("thumbnail") else ""
    m = record.get("accuracy_metrics", {})
    perf = (f"On held-out test images this model reached AUROC {m.get('auroc', 0):.2f} for DR; at its review threshold it found "
            f"{m.get('sensitivity', 0):.0%} of DR cases (sensitivity) and a LOW result does NOT rule out DR. "
            f"Model stage: {E(r.get('model_stage') or '?')}.") if m else ""
    ctx = "".join(f"<tr><th>{E(str(k))}</th><td>{E(str(v))}</td></tr>" for k, v in (r.get("clinical_context") or {}).items()) or "<tr><td>none supplied</td></tr>"
    grades = "".join(f"<tr><td><b>{E(g)}</b></td><td>{E(v['followup'])}</td><td>{E(v['medication'])}</td></tr>" for g, v in guidelines["by_confirmed_grade"].items())
    if r.get("reviewed_at"):
        rev = (f"<tr><th>Confirmed grade</th><td><b>{E(r['confirmed_grade'])}</b> ({E(r['review_decision'])})</td></tr>"
               f"<tr><th>Reviewed by</th><td>{E(r['reviewer_id'])} at {r['reviewed_at']}</td></tr><tr><th>Rationale</th><td>{E(r.get('review_rationale') or '-')}</td></tr>")
    else:
        rev = "<tr><th>Confirmed grade</th><td>&nbsp; (pending clinician review)</td></tr><tr><th>Name, signature, date</th><td>&nbsp;</td></tr>"
    return (f"<!doctype html><meta charset=utf-8><title>DR report {E(r['result_id'])}</title><style>{CSS}</style><div class='w'>"
            f"<h1>Retinal screening report <span class='badge {r['triage']}'>{r['triage']}</span></h1>"
            f"<div class='small'>Result {E(r['result_id'])} | node {E(r['hospital_node_id'])} | model {E(r['model_version'])} | {r['created_at']}</div>"
            f"<div class='warn'><b>{E(DISCLAIMER)}</b> {E(perf)} Guideline text status: <b>{E(guidelines.get('status', ''))}</b>.</div>"
            f"<div class='card'>{img}<b>{E(r['ai_finding'])}</b><div class='small'>{E(r['rationale'] or '')}</div>{bars}"
            f"<div class='small'>Eye: {E(r.get('eye') or '?')} | flags: {E(', '.join(r.get('flags') or []) or 'none')}</div><div style='clear:both'></div></div>"
            f"<h2>Suggested next steps (from clinician-owned guidelines)</h2><div class='card'><table>"
            f"<tr><th>Follow-up</th><td>{E(_g(r, 'followup', guidelines))}</td></tr><tr><th>Management</th><td>{E(_g(r, 'management', guidelines))}</td></tr>"
            f"<tr><th>Medication note</th><td>{E(_g(r, 'medication', guidelines))}</td></tr></table></div>"
            f"<h2>Clinical context supplied</h2><div class='card'><table>{ctx}</table></div>"
            f"<h2>If the clinician confirms a grade</h2><div class='card'><table><tr><th>Grade</th><th>Follow-up</th><th>Treatment options (specialist decides, no doses)</th></tr>{grades}</table></div>"
            f"<h2>Clinician review</h2><div class='card'><table>{rev}</table></div></div>")


def _g(r: dict, field: str, guidelines: dict) -> str:
    """Look the suggestion text up again from the finding key stored in the label, so reports always show current guideline text."""
    for f in guidelines["findings"].values():
        if r["ai_finding"].startswith(f["label"]):
            return f[field]
    return "-"
