"""Load sample patients + trial into the running database (no HTTP needed)."""
import json
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from app import db
from app.evaluation import load_bundle
from app.nlp import redact_phi
from app.main import _seed

db.init(_seed())
pats, trial, _ = load_bundle()
for p in pats:
    found = {}
    for n in p["notes"]:
        n["text"], f = redact_phi(n["text"])
        for k, v in f.items(): found[k] = found.get(k, 0) + v
    db.save_patient(p, found)
db.save_trial(trial)
print(f"seeded {len(pats)} patients and trial {trial['id']}")
