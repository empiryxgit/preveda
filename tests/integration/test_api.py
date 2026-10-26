import json
import jwt
import sqlalchemy as sa
from tests.conftest import fundus_like


def post(c, **kw):
    return c.post("/madhu/predict/dr", files={"image": ("eye.jpg", fundus_like(), "image/jpeg")}, **kw)


def test_health_and_ready(client):
    assert client.get("/health").json()["status"] == "ok"
    r = client.get("/ready").json()
    assert r["ready"] and r["model_loaded"] and r["database"]


def test_predict_returns_triage_and_suggestions(client):
    r = post(client, data={"patient_ref": "P-1", "eye": "Left", "clinical_context": json.dumps({"age": 60})})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["triage"] in {"HIGH", "MEDIUM", "LOW", "RETAKE"}
    assert abs(sum(j["probabilities"].values()) - 1) < 1e-3
    assert j["model"]["signature_verified"] and j["model"]["stage"] == "STAGING"
    assert j["suggested_followup"] and "not a diagnosis" in j["disclaimer"]
    assert r.headers["X-Request-ID"] and r.headers["X-Hospital-Node"] == "NODE-TEST"
    print("latency_ms", j["latency_ms"])
    assert j["latency_ms"] < 3000


def test_result_report_and_pseudonymisation(client):
    j = post(client, data={"patient_ref": "PATIENT-123"}).json()
    got = client.get(f"/madhu/dr/results/{j['result_id']}").json()
    assert "thumbnail" not in got and got["patient_hash"] and "PATIENT-123" not in json.dumps(got)
    html = client.get(j["report_url"]).text
    assert j["triage"] in html and "not a diagnosis" in html
    assert client.get("/madhu/dr/results/nope").status_code == 404


def test_review_logged_and_audit_chain(client):
    rid = post(client).json()["result_id"]
    assert client.post(f"/madhu/dr/results/{rid}/review", json={"confirmed_grade": "Banana", "decision": "accept"}).status_code == 422
    ok = client.post(f"/madhu/dr/results/{rid}/review",
                     json={"confirmed_grade": "Moderate NPDR", "decision": "override", "rationale": "exudates near macula"})
    assert ok.status_code == 200 and "anti-VEGF" in ok.json()["plan_for_grade"]["medication"]
    got = client.get(f"/madhu/dr/results/{rid}").json()
    assert got["reviewer_id"] and got["confirmed_grade"] == "Moderate NPDR" and got["reviewed_at"]
    v = client.get("/audit/verify").json()
    assert v == {"intact": True, "entries": 2, "first_bad_id": None}


def test_audit_tamper_detected(client):
    post(client); post(client)
    eng = client.app.state.store.engine
    with eng.begin() as c:
        c.execute(sa.text("UPDATE audit_log SET actor='mallory' WHERE id=1"))
    v = client.get("/audit/verify").json()
    assert v["intact"] is False and v["first_bad_id"] == 1


def test_bad_inputs(client, env):
    assert client.post("/madhu/predict/dr", files={"image": ("x.jpg", b"not an image", "image/jpeg")}).status_code == 400
    assert post(client, data={"clinical_context": "[1,2]"}).status_code == 400
    assert post(client, data={"abha_hash": "123"}).status_code == 400


def test_upload_size_limit(env):
    from fastapi.testclient import TestClient
    from preveda_dr.api.main import create_app
    from preveda_dr.core.settings import get_settings
    env.setenv("PREVEDA_MAX_UPLOAD_MB", "1"); get_settings.cache_clear()
    with TestClient(create_app()) as c:
        r = c.post("/madhu/predict/dr", files={"image": ("big.jpg", b"\0" * 1_200_000, "image/jpeg")})
        assert r.status_code == 413


def test_metrics_endpoint(client):
    post(client)
    assert "madhu_dr_predictions_total" in client.get("/metrics").text


def test_jwt_roles_and_node_header(env):          # AC-S4: 401 without JWT, 403 for role violations
    from fastapi.testclient import TestClient
    from preveda_dr.api.main import create_app
    from preveda_dr.core.settings import get_settings
    env.setenv("PREVEDA_AUTH_MODE", "hs256"); env.setenv("PREVEDA_JWT_SECRET", "s" * 40); get_settings.cache_clear()
    tok = lambda roles: jwt.encode({"preferred_username": "dr.shah", "realm_access": {"roles": roles}}, "s" * 40, algorithm="HS256")
    hdr = lambda roles, node="NODE-TEST": {"Authorization": f"Bearer {tok(roles)}", "X-Hospital-Node": node}
    f = {"image": ("e.jpg", fundus_like(), "image/jpeg")}
    with TestClient(create_app()) as c:
        assert c.post("/madhu/predict/dr", files=f).status_code == 401
        assert c.post("/madhu/predict/dr", files=f, headers={"Authorization": "Bearer junk"}).status_code == 401
        assert c.post("/madhu/predict/dr", files=f, headers=hdr(["data_analyst"])).status_code == 403
        assert c.post("/madhu/predict/dr", files=f, headers=hdr(["clinician"], node="OTHER")).status_code == 403
        r = c.post("/madhu/predict/dr", files=f, headers=hdr(["clinician"]))
        assert r.status_code == 200
        assert c.get("/audit/verify", headers=hdr(["clinician"])).status_code == 403
        assert c.get("/audit/verify", headers=hdr(["auditor"])).status_code == 200
        assert c.get("/health").status_code == 200       # health stays open for k8s probes
