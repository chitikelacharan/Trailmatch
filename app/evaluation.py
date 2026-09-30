"""Measurable evaluation framework: runs the engine on a gold-labelled set and reports
decision accuracy, false-positive (unsafe) rates, missing-evidence recall, criterion accuracy,
grounding rate. Used by the /evaluate API, the CLI, and as a CI gate."""
import json
import pathlib
from datetime import date

from .engine import match
from .protocol import parse_criteria_text

DATA = pathlib.Path(__file__).resolve().parent.parent / "data"
DECISIONS = ["ELIGIBLE", "NEEDS_REVIEW", "INELIGIBLE"]


def load_bundle():
    pats = json.loads((DATA / "sample_patients.json").read_text())
    trial = json.loads((DATA / "sample_trial.json").read_text())
    gold = json.loads((DATA / "gold_labels.json").read_text())
    trial["criteria"] = parse_criteria_text(trial["criteria_text"])
    return pats, trial, gold


def run_eval(patients=None, trial=None, gold=None):
    if patients is None:
        patients, trial, gold = load_bundle()
    as_of = date.fromisoformat(gold["as_of"])
    labels = gold["labels"]
    conf = {t: {p: 0 for p in DECISIONS} for t in DECISIONS}
    rows, crit_ok, crit_n, miss_tp, miss_fn, miss_fp, grounding_fail = [], 0, 0, 0, 0, 0, 0
    for p in patients:
        if p["id"] not in labels:
            continue
        g = labels[p["id"]]
        r = match(p, trial, as_of)
        conf[g["decision"]][r["decision"]] += 1
        got_missing = {m["criterion_id"] for m in r["missing_evidence"]}
        exp_missing = set(g.get("missing", []))
        miss_tp += len(got_missing & exp_missing); miss_fn += len(exp_missing - got_missing); miss_fp += len(got_missing - exp_missing)
        states = {c["id"]: c["state"] for c in r["criteria"]}
        for cid, st in g.get("states", {}).items():
            crit_n += 1; crit_ok += states.get(cid) == st
        grounding_fail += r["grounding_failures"]
        rows.append(dict(patient_id=p["id"], expected=g["decision"], predicted=r["decision"], ok=g["decision"] == r["decision"],
                         confidence=r["confidence"]))
    n = len(rows)
    non_elig = sum(sum(conf[t].values()) for t in ("NEEDS_REVIEW", "INELIGIBLE"))
    pred_elig = sum(conf[t]["ELIGIBLE"] for t in DECISIONS)
    fp = conf["NEEDS_REVIEW"]["ELIGIBLE"] + conf["INELIGIBLE"]["ELIGIBLE"]
    true_elig = sum(conf["ELIGIBLE"].values())
    metrics = dict(
        n_patients=n,
        decision_accuracy=round(sum(r["ok"] for r in rows) / n, 4) if n else None,
        eligible_false_positive_rate=round(fp / non_elig, 4) if non_elig else 0.0,
        eligible_precision=round(conf["ELIGIBLE"]["ELIGIBLE"] / pred_elig, 4) if pred_elig else None,
        eligible_recall=round(conf["ELIGIBLE"]["ELIGIBLE"] / true_elig, 4) if true_elig else None,
        unsafe_errors=conf["INELIGIBLE"]["ELIGIBLE"],                 # ineligible patient marked eligible
        wrongly_excluded=conf["ELIGIBLE"]["INELIGIBLE"],              # eligible patient hard-excluded (missed opportunity)
        missing_evidence_recall=round(miss_tp / (miss_tp + miss_fn), 4) if (miss_tp + miss_fn) else 1.0,
        missing_evidence_precision=round(miss_tp / (miss_tp + miss_fp), 4) if (miss_tp + miss_fp) else 1.0,
        criterion_state_accuracy=round(crit_ok / crit_n, 4) if crit_n else None,
        grounding_failures=grounding_fail,
        confusion_matrix=conf, per_patient=rows)
    metrics["gate_passed"] = (metrics["unsafe_errors"] == 0 and metrics["eligible_false_positive_rate"] == 0
                              and grounding_fail == 0 and (metrics["decision_accuracy"] or 0) >= 0.9)
    return metrics


if __name__ == "__main__":
    m = run_eval()
    print(json.dumps({k: v for k, v in m.items() if k != "per_patient"}, indent=2))
    for r in m["per_patient"]:
        print(("OK  " if r["ok"] else "FAIL"), r["patient_id"], "expected", r["expected"], "got", r["predicted"])
    raise SystemExit(0 if m["gate_passed"] else 1)
