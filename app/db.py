"""Persistence via SQLAlchemy Core (SQLite for dev, PostgreSQL in production).
PHI-bearing payloads are stored Fernet-encrypted. Audit log is hash-chained (tamper-evident)."""
import hashlib, json, threading
from datetime import datetime, timezone

from sqlalchemy import (Column, DateTime, Integer, MetaData, String, Table, Text, create_engine, insert, select, text, update)

from . import config, security

_kw = {"connect_args": {"check_same_thread": False}} if config.DATABASE_URL.startswith("sqlite") else {"pool_size": 10, "pool_pre_ping": True}
engine = create_engine(config.DATABASE_URL, future=True, **_kw)
meta = MetaData()
users = Table("users", meta, Column("username", String(64), primary_key=True), Column("pw_hash", Text), Column("role", String(16)))
patients = Table("patients", meta, Column("id", String(64), primary_key=True), Column("blob", Text),
                 Column("phi_findings", Text), Column("created_at", DateTime))
trials = Table("trials", meta, Column("id", String(64), primary_key=True), Column("title", Text),
               Column("criteria_json", Text), Column("source_text", Text), Column("created_at", DateTime))
matches = Table("matches", meta, Column("id", Integer, primary_key=True, autoincrement=True), Column("patient_id", String(64)),
                Column("trial_id", String(64)), Column("decision", String(16)), Column("result", Text),
                Column("created_at", DateTime), Column("review_status", String(24), default="pending"),
                Column("reviewer", String(64)), Column("review_note", Text))
audit = Table("audit", meta, Column("id", Integer, primary_key=True, autoincrement=True), Column("ts", String(40)),
              Column("actor", String(64)), Column("action", String(64)), Column("resource", String(128)),
              Column("detail", Text), Column("prev_hash", String(64)), Column("hash", String(64)))
_lock = threading.Lock()
now = lambda: datetime.now(timezone.utc).replace(tzinfo=None)


def init(seed=None):
    meta.create_all(engine)
    if seed:
        with engine.begin() as c:
            for u, pw, role in seed:
                if not c.execute(select(users).where(users.c.username == u)).first():
                    c.execute(insert(users).values(username=u, pw_hash=security.hash_password(pw), role=role))


def get_user(u):
    with engine.connect() as c:
        return c.execute(select(users).where(users.c.username == u)).mappings().first()


def log(actor, action, resource="", detail=""):
    """Append to the hash-chained audit log. Never store raw PHI in `detail`."""
    with _lock, engine.begin() as c:
        if engine.dialect.name == "postgresql":
            c.execute(text("SELECT pg_advisory_xact_lock(424242)"))
        prev = c.execute(select(audit.c.hash).order_by(audit.c.id.desc()).limit(1)).scalar() or "GENESIS"
        ts = datetime.now(timezone.utc).isoformat()
        h = hashlib.sha256(json.dumps([prev, ts, actor, action, resource, detail]).encode()).hexdigest()
        c.execute(insert(audit).values(ts=ts, actor=actor, action=action, resource=resource, detail=detail, prev_hash=prev, hash=h))


def verify_audit():
    with engine.connect() as c:
        rows = c.execute(select(audit).order_by(audit.c.id)).mappings().all()
    prev = "GENESIS"
    for r in rows:
        h = hashlib.sha256(json.dumps([prev, r["ts"], r["actor"], r["action"], r["resource"], r["detail"]]).encode()).hexdigest()
        if r["prev_hash"] != prev or r["hash"] != h:
            return dict(valid=False, broken_at=r["id"], entries=len(rows))
        prev = h
    return dict(valid=True, entries=len(rows))


def audit_list(limit=100):
    with engine.connect() as c:
        return [dict(r) for r in c.execute(select(audit).order_by(audit.c.id.desc()).limit(limit)).mappings()]


def save_patient(p, phi):
    blob = security.encrypt(json.dumps(p))
    with engine.begin() as c:
        if c.execute(select(patients.c.id).where(patients.c.id == p["id"])).first():
            c.execute(update(patients).where(patients.c.id == p["id"]).values(blob=blob, phi_findings=json.dumps(phi)))
        else:
            c.execute(insert(patients).values(id=p["id"], blob=blob, phi_findings=json.dumps(phi), created_at=now()))


def get_patient(pid):
    with engine.connect() as c:
        r = c.execute(select(patients.c.blob).where(patients.c.id == pid)).first()
    return json.loads(security.decrypt(r[0])) if r else None


def list_patient_ids():
    with engine.connect() as c:
        return [r[0] for r in c.execute(select(patients.c.id).order_by(patients.c.id))]


def save_trial(t):
    with engine.begin() as c:
        c.execute(text("DELETE FROM trials WHERE id=:i"), {"i": t["id"]})
        c.execute(insert(trials).values(id=t["id"], title=t.get("title", ""), criteria_json=json.dumps(t["criteria"]),
                                        source_text=t.get("criteria_text", ""), created_at=now()))


def get_trial(tid):
    with engine.connect() as c:
        r = c.execute(select(trials).where(trials.c.id == tid)).mappings().first()
    return dict(id=r["id"], title=r["title"], criteria=json.loads(r["criteria_json"]), criteria_text=r["source_text"]) if r else None


def list_trials():
    with engine.connect() as c:
        return [dict(id=r["id"], title=r["title"], n_criteria=len(json.loads(r["criteria_json"])))
                for r in c.execute(select(trials)).mappings()]


def save_match(res):
    with engine.begin() as c:
        r = c.execute(insert(matches).values(patient_id=res["patient_id"], trial_id=res["trial_id"], decision=res["decision"],
                                             result=security.encrypt(json.dumps(res)), created_at=now(), review_status="pending"))
        return r.inserted_primary_key[0]


def get_match(mid):
    with engine.connect() as c:
        r = c.execute(select(matches).where(matches.c.id == mid)).mappings().first()
    if not r:
        return None
    out = json.loads(security.decrypt(r["result"]))
    out.update(match_id=r["id"], review_status=r["review_status"], reviewer=r["reviewer"], review_note=r["review_note"])
    return out


def review_match(mid, status, reviewer, note):
    with engine.begin() as c:
        r = c.execute(update(matches).where(matches.c.id == mid).values(review_status=status, reviewer=reviewer, review_note=note))
        return r.rowcount
