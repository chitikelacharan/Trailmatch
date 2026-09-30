"""TrialMatch API. Run: uvicorn app.main:app --reload"""
import hashlib, json, os, pathlib, time
from contextlib import asynccontextmanager
from datetime import date

from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from . import cache, config, db, evaluation, metrics, security
from .engine import ENGINE_VERSION, match
from .nlp import redact_phi, scan_phi
from .protocol import parse_criteria_text, validate_criteria

STATIC = pathlib.Path(__file__).resolve().parent.parent / "static"
DECISION_RANK = {"ELIGIBLE": 0, "NEEDS_REVIEW": 1, "INELIGIBLE": 2}


def _seed():
    if config.IS_PROD and not os.getenv("ADMIN_PASSWORD"):
        return []          # production: users must be provisioned explicitly
    g = lambda k, dflt: os.getenv(k, dflt)
    return [("admin", g("ADMIN_PASSWORD", "Admin#12345"), "admin"),
            ("coordinator", g("COORDINATOR_PASSWORD", "Coord#12345"), "coordinator"),
            ("auditor", g("AUDITOR_PASSWORD", "Audit#12345"), "auditor")]


@asynccontextmanager
async def lifespan(app):
    db.init(_seed())
    yield


app = FastAPI(title="TrialMatch - Clinical Trial Eligibility Matcher", version=ENGINE_VERSION, lifespan=lifespan)
if config.CORS_ORIGINS:
    app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def sec_headers(request: Request, call_next):
    t = time.time()
    resp = await call_next(request)
    resp.headers.update({"X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer",
                         "Cache-Control": "no-store", "Content-Security-Policy": "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'",
                         "Strict-Transport-Security": "max-age=63072000; includeSubDomains"})
    metrics.inc("http_requests_total", f'status="{resp.status_code}"')
    metrics.observe("http_request_seconds", time.time() - t)
    return resp


# ------------------------------------------------------------------ ops
@app.get("/health")
def health():
    return {"status": "ok", "version": ENGINE_VERSION}


@app.get("/ready")
def ready():
    try:
        db.list_patient_ids(); return {"status": "ready"}
    except Exception:
        raise HTTPException(503, "db unavailable")


@app.get("/metrics", response_class=PlainTextResponse)
def prom():
    return metrics.render()


# ------------------------------------------------------------------ auth
@app.post("/auth/login", dependencies=[Depends(security.rate_limit)])
def login(body: dict = Body(...)):
    u = db.get_user(body.get("username", ""))
    if not u or not security.verify_password(body.get("password", ""), u["pw_hash"]):
        db.log(body.get("username", "?"), "login_failed"); metrics.inc("login_failures_total")
        raise HTTPException(401, "Invalid credentials")
    db.log(u["username"], "login")
    return {"access_token": security.create_token(u["username"], u["role"]), "role": u["role"], "token_type": "bearer"}


# ------------------------------------------------------------------ patients
def _validate_patient(p):
    if not isinstance(p, dict) or not p.get("id"):
        raise HTTPException(422, "each patient needs an 'id'")
    for k in ("conditions", "labs", "medications", "notes"):
        if not isinstance(p.get(k, []), list):
            raise HTTPException(422, f"'{k}' must be a list")
    p.setdefault("demographics", {})
    for i, n in enumerate(p.get("notes") or []):
        n.setdefault("id", f"{p['id']}-N{i+1}")


@app.post("/patients")
def ingest(body: dict = Body(...), strict_deid: bool = Query(False), user=Depends(security.require("admin", "coordinator"))):
    """Ingest de-identified patient(s). PHI-like patterns are redacted (or rejected with strict_deid=true)."""
    items = body.get("patients") or [body]
    report = []
    for p in items:
        _validate_patient(p)
        found_total = {}
        for n in p.get("notes") or []:
            found = scan_phi(n.get("text", ""))
            if found and strict_deid:
                raise HTTPException(422, f"PHI patterns detected in {n['id']}: {sorted(found)}")
            n["text"], f = redact_phi(n.get("text", ""))
            for k, v in f.items(): found_total[k] = found_total.get(k, 0) + v
        db.save_patient(p, found_total)
        db.log(user["sub"], "patient_ingest", p["id"], f"phi_redactions={sum(found_total.values())}")
        metrics.inc("patients_ingested_total")
        report.append(dict(id=p["id"], phi_redacted=found_total))
    return {"ingested": len(report), "report": report}


@app.get("/patients")
def patients(user=Depends(security.require("admin", "coordinator", "auditor"))):
    return {"patients": db.list_patient_ids()}


@app.get("/patients/{pid}")
def patient(pid: str, user=Depends(security.require("admin", "coordinator"))):
    p = db.get_patient(pid)
    if not p: raise HTTPException(404, "not found")
    db.log(user["sub"], "patient_view", pid)
    return p


# ------------------------------------------------------------------ trials
@app.post("/trials")
def create_trial(body: dict = Body(...), user=Depends(security.require("admin", "coordinator"))):
    if not body.get("id"): raise HTTPException(422, "'id' required")
    criteria = body.get("criteria") or parse_criteria_text(body.get("criteria_text", ""))
    if not criteria: raise HTTPException(422, "provide 'criteria' or parseable 'criteria_text'")
    errs = validate_criteria(criteria)
    if errs: raise HTTPException(422, errs)
    body["criteria"] = criteria
    db.save_trial(body); cache.clear()
    db.log(user["sub"], "trial_upsert", body["id"])
    return {"id": body["id"], "criteria": criteria,
            "unparsed": [c["id"] for c in criteria if c["kind"] == "manual" and not c.get("screening_only")]}


@app.get("/trials")
def trials(user=Depends(security.require("admin", "coordinator", "auditor"))):
    return {"trials": db.list_trials()}


@app.get("/trials/{tid}")
def trial(tid: str, user=Depends(security.require("admin", "coordinator", "auditor"))):
    t = db.get_trial(tid)
    if not t: raise HTTPException(404, "not found")
    return t


# ------------------------------------------------------------------ matching
def _run(pid, t, as_of, actor):
    p = db.get_patient(pid)
    if not p: raise HTTPException(404, f"patient {pid} not found")
    key = "m:" + hashlib.sha256(json.dumps([p, t["criteria"], str(as_of), ENGINE_VERSION], sort_keys=True).encode()).hexdigest()
    res = cache.get(key)
    if res:
        metrics.inc("match_cache_hits_total")
    else:
        t0 = time.time()
        res = match(p, t, as_of); res["trial_id"] = t["id"]
        metrics.observe("match_seconds", time.time() - t0)
        cache.put(key, res); metrics.inc("match_cache_misses_total")
    metrics.inc("match_decisions_total", f'decision="{res["decision"]}"')
    res = dict(res); res["match_id"] = db.save_match(res)
    db.log(actor, "match", f"{pid}:{t['id']}", res["decision"])
    return res


def _as_of(v):
    try: return date.fromisoformat(v) if v else date.today()
    except ValueError: raise HTTPException(422, "as_of must be YYYY-MM-DD")


@app.post("/match")
def match_one(body: dict = Body(...), user=Depends(security.require("admin", "coordinator"))):
    t = db.get_trial(body.get("trial_id", ""))
    if not t: raise HTTPException(404, "trial not found")
    return _run(body.get("patient_id", ""), t, _as_of(body.get("as_of")), user["sub"])


@app.post("/match/batch")
def match_batch(body: dict = Body(...), user=Depends(security.require("admin", "coordinator"))):
    t = db.get_trial(body.get("trial_id", ""))
    if not t: raise HTTPException(404, "trial not found")
    as_of, out = _as_of(body.get("as_of")), []
    for pid in db.list_patient_ids():
        r = _run(pid, t, as_of, user["sub"])
        out.append(dict(match_id=r["match_id"], patient_id=pid, decision=r["decision"], likely_ineligible=r["likely_ineligible"],
                        confidence=r["confidence"], criteria_satisfied=r["criteria_satisfied"],
                        n_missing=len(r["missing_evidence"]), summary=r["summary"]))
    out.sort(key=lambda r: (DECISION_RANK[r["decision"]], r["likely_ineligible"], -r["confidence"]))
    return {"trial_id": t["id"], "as_of": str(as_of), "results": out,
            "counts": {k: sum(1 for r in out if r["decision"] == k) for k in DECISION_RANK}}


@app.get("/matches/{mid}")
def get_match(mid: int, user=Depends(security.require("admin", "coordinator", "auditor"))):
    m = db.get_match(mid)
    if not m: raise HTTPException(404, "not found")
    db.log(user["sub"], "match_view", str(mid))
    return m


@app.post("/matches/{mid}/review")
def review(mid: int, body: dict = Body(...), user=Depends(security.require("admin", "coordinator"))):
    status = body.get("status")
    if status not in ("confirmed", "rejected", "info_requested"):
        raise HTTPException(422, "status must be confirmed|rejected|info_requested")
    if not db.review_match(mid, status, user["sub"], body.get("note", "")):
        raise HTTPException(404, "not found")
    db.log(user["sub"], "match_review", str(mid), status)
    return {"match_id": mid, "review_status": status}


# ------------------------------------------------------------------ audit & evaluation
@app.get("/audit")
def audit(limit: int = 100, user=Depends(security.require("admin", "auditor", "coordinator"))):
    return {"entries": db.audit_list(min(limit, 1000)), "integrity": db.verify_audit()}


@app.post("/evaluate")
def evaluate(user=Depends(security.require("admin", "auditor", "coordinator"))):
    m = evaluation.run_eval()
    db.log(user["sub"], "evaluation_run", "gold", f"acc={m['decision_accuracy']} fp={m['eligible_false_positive_rate']}")
    for k in ("decision_accuracy", "eligible_false_positive_rate", "unsafe_errors"):
        metrics.counters[(f"eval_{k}", "")] = m[k]
    return m


if STATIC.exists():
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC / "index.html")
