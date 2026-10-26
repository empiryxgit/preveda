"""Web-app API: dummy login, roles, folder settings, scan, results, review."""
import time
from tests.conftest import fundus_like


def login(c, user, pw):
    r = c.post("/ui-api/login", json={"username": user, "password": pw})
    return r, ({"Authorization": f"Bearer {r.json()['token']}"} if r.status_code == 200 else None)


def test_login_and_protection(client):
    assert client.get("/ui-api/dashboard").status_code == 401
    assert login(client, "doctor", "wrong")[0].status_code == 401
    r, h = login(client, "doctor", "doctor123")
    assert r.json()["user"]["role"] == "clinician"
    assert client.get("/ui-api/me", headers=h).json()["name"] == "Dr. Demo"
    assert client.get("/", follow_redirects=False).status_code in (302, 307)
    assert client.get("/ui/").status_code == 200


def test_roles_on_settings(client, tmp_path):
    _, doc = login(client, "doctor", "doctor123")
    _, adm = login(client, "admin", "admin123")
    body = {"watch_path": str(tmp_path), "auto_scan": False, "scan_interval": 60}
    assert client.put("/ui-api/settings", json=body, headers=doc).status_code == 403
    assert client.put("/ui-api/settings", json=body, headers=adm).status_code == 200
    assert client.get("/ui-api/settings", headers=doc).json()["watch_path"] == str(tmp_path)


def test_path_validation(client, tmp_path):
    _, adm = login(client, "admin", "admin123")
    t = lambda p: client.post("/ui-api/settings/test-path", json={"path": p}, headers=adm).json()
    assert "not shared" in t("D:\\Photos")["message"]
    assert not t(str(tmp_path / "nope"))["exists"]
    assert t(str(tmp_path))["image_count"] == 0
    (tmp_path / "a.jpg").write_bytes(fundus_like(1))
    assert t(str(tmp_path))["image_count"] == 1


def test_scan_results_review(client, tmp_path):
    for i in range(3):
        (tmp_path / f"7000{i}_LE_x.jpg").write_bytes(fundus_like(i * 10))
    (tmp_path / "notes.txt").write_text("ignored")
    (tmp_path / "bad.jpg").write_bytes(b"not an image")
    _, adm = login(client, "admin", "admin123")
    client.put("/ui-api/settings", json={"watch_path": str(tmp_path), "auto_scan": False, "scan_interval": 60}, headers=adm)
    assert client.post("/ui-api/scan", headers=adm).json()["started"]
    for _ in range(60):
        s = client.get("/ui-api/scan/status", headers=adm).json()
        if not s["running"]:
            break
        time.sleep(0.5)
    assert s["new"] == 3 and s["failed"] == 1 and s["total"] == 4
    client.post("/ui-api/scan", headers=adm); time.sleep(3)   # second scan: nothing new
    assert client.get("/ui-api/scan/status", headers=adm).json()["new"] == 0
    res = client.get("/ui-api/results", headers=adm).json()
    assert res["total"] == 3 and res["items"][0]["record"].startswith("7000")
    rid = res["items"][0]["result_id"]
    d = client.get(f"/ui-api/results/{rid}", headers=adm).json()
    assert d["suggested_followup"] and "No DR" in d["grades"]
    assert client.get(f"/ui-api/results/{rid}/report", headers=adm).status_code == 200
    r = client.post(f"/ui-api/results/{rid}/review", json={"confirmed_grade": "No DR", "decision": "accept"}, headers=adm)
    assert r.status_code == 200
    assert client.get(f"/ui-api/results/{rid}", headers=adm).json()["review"]["grade"] == "No DR"
    dash = client.get("/ui-api/dashboard", headers=adm).json()
    assert dash["totals"]["total"] == 3 and dash["audit"]["intact"]


def test_demo_login_disabled_with_real_auth(env):
    from fastapi.testclient import TestClient
    from preveda_dr.api.main import create_app
    from preveda_dr.core.settings import get_settings
    env.setenv("PREVEDA_AUTH_MODE", "hs256"); env.setenv("PREVEDA_JWT_SECRET", "s"); get_settings.cache_clear()
    with TestClient(create_app()) as c:
        assert c.post("/ui-api/login", json={"username": "admin", "password": "admin123"}).status_code == 404


def test_two_listeners_share_state(env):
    """API app and web app are separate listeners but share one model/db (python -m preveda_dr.server)."""
    from fastapi.testclient import TestClient
    from preveda_dr.api.main import create_pair
    api, web = create_pair()
    with TestClient(api) as a:
        w = TestClient(web)
        assert a.get("/ready").json()["ready"]
        assert a.get("/docs").status_code == 200 and a.get("/ui/").status_code == 404 and a.post("/ui-api/login", json={}).status_code == 404
        assert w.get("/ui/").status_code == 200 and w.get("/docs").status_code == 404
        assert w.post("/madhu/predict/dr").status_code == 404 and w.get("/health").json()["status"] == "ok"
        tok = w.post("/ui-api/login", json={"username": "doctor", "password": "doctor123"}).json()["token"]
        assert w.get("/ui-api/system", headers={"Authorization": f"Bearer {tok}"}).json()["model"]["loaded"]


def test_windows_path_is_mapped_to_mounted_drive(client, tmp_path, monkeypatch):
    from preveda_dr.core.settings import get_settings
    (tmp_path / "Hospital" / "Fundus").mkdir(parents=True)
    (tmp_path / "Hospital" / "Fundus" / "a.jpg").write_bytes(fundus_like(2))
    monkeypatch.setenv("PREVEDA_PATH_MAP", f"D:={tmp_path},C:=/host/c"); get_settings.cache_clear()
    _, adm = login(client, "admin", "admin123")
    t = lambda p: client.post("/ui-api/settings/test-path", json={"path": p}, headers=adm).json()
    v = t("D:\\Hospital\\Fundus")
    assert v["image_count"] == 1 and v["resolved"] == f"{tmp_path}/Hospital/Fundus"
    assert "not shared" in t("E:\\x")["message"] and "not allowed" in t("D:\\a\\..\\b")["message"]
    client.put("/ui-api/settings", json={"watch_path": "D:\\Hospital\\Fundus", "auto_scan": False, "scan_interval": 60}, headers=adm)
    client.post("/ui-api/scan", headers=adm)
    import time
    for _ in range(40):
        s = client.get("/ui-api/scan/status", headers=adm).json()
        if not s["running"]:
            break
        time.sleep(0.5)
    assert s["new"] == 1
