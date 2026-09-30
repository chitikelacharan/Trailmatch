import json, os, tempfile
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/t.db"
from fastapi.testclient import TestClient
from app.main import app
from app.evaluation import load_bundle


def _login(c, u, p):
    r = c.post("/auth/login", json={"username": u, "password": p})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_full_flow():
    with TestClient(app) as c:
        assert c.get("/health").status_code == 200
        assert c.get("/patients").status_code == 401                       # auth required
        assert c.post("/auth/login", json={"username": "admin", "password": "bad"}).status_code == 401
        co, au = _login(c, "coordinator", "Coord#12345"), _login(c, "auditor", "Audit#12345")
        pats, trial, _ = load_bundle()
        r = c.post("/patients", json={"patients": pats}, headers=co)
        assert r.status_code == 200 and r.json()["ingested"] == 12
        p10 = next(x for x in r.json()["report"] if x["id"] == "P010")
        assert p10["phi_redacted"].get("SSN") == 1                          # PHI redacted on ingest
        assert c.post("/patients", json=pats[9], params={"strict_deid": True}, headers=co).status_code in (200, 422)
        r = c.post("/trials", json={"id": "DIAB-201", "title": "x", "criteria_text": trial["criteria_text"]}, headers=co)
        assert r.status_code == 200 and r.json()["unparsed"] == []
        r = c.post("/match", json={"patient_id": "P002", "trial_id": "DIAB-201", "as_of": "2026-09-30"}, headers=co)
        assert r.status_code == 200 and r.json()["decision"] == "INELIGIBLE"
        mid = r.json()["match_id"]
        r = c.post("/match/batch", json={"trial_id": "DIAB-201", "as_of": "2026-09-30"}, headers=co)
        assert r.json()["counts"]["ELIGIBLE"] == 4
        assert c.get("/patients/P001", headers=au).status_code == 403       # auditors cannot read PHI
        assert c.post(f"/matches/{mid}/review", json={"status": "confirmed", "note": "ok"}, headers=co).status_code == 200
        a = c.get("/audit", headers=au).json()
        assert a["integrity"]["valid"] and len(a["entries"]) > 5
        assert c.post("/evaluate", headers=au).json()["gate_passed"]
        assert "match_decisions_total" in c.get("/metrics").text
