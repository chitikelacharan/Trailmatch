from datetime import date
from app.engine import match
from app.evaluation import load_bundle, run_eval
from app.nlp import find_mentions, redact_phi, scan_phi
from app.terminology import CONDITIONS
from app.protocol import parse_criteria_text, validate_criteria

AS_OF = date(2026, 9, 30)
PATS, TRIAL, GOLD = load_bundle()
BY = {p["id"]: p for p in PATS}


def res(pid):
    return match(BY[pid], TRIAL, AS_OF)


def st(r, cid):
    return next(c for c in r["criteria"] if c["id"] == cid)


def test_eval_gate():
    m = run_eval()
    assert m["gate_passed"] and m["decision_accuracy"] == 1.0 and m["unsafe_errors"] == 0


def test_missing_evidence_flagged():
    r = res("P003")
    ids = {m["criterion_id"] for m in r["missing_evidence"]}
    assert r["decision"] == "NEEDS_REVIEW" and {"I3", "I5"} <= ids


def test_negation_and_family_not_counted():
    r = res("P005")
    assert st(r, "E2")["state"] == "FALSE" and st(r, "E4")["state"] == "FALSE" and r["decision"] == "ELIGIBLE"


def test_ambiguous_abbreviation_needs_review():
    c = st(res("P006"), "E2")
    assert c["state"] == "UNKNOWN" and "ambiguous_abbreviation" in c["flags"]


def test_ambiguous_abbreviation_resolved_by_context():
    m = find_mentions("Troponin elevated, acute MI, stent placed.", CONDITIONS["myocardial_infarction"], "myocardial_infarction")
    assert m and m[0]["cls"] == "positive"


def test_miscoded_diagnosis_conflict():
    r = res("P004")
    assert st(r, "I2")["state"] == "CONFLICT" and r["decision"] == "NEEDS_REVIEW"


def test_legacy_icd9_and_unit_conversion():
    r = res("P007")
    assert st(r, "I2")["state"] == "TRUE" and st(r, "I3")["state"] == "TRUE"
    assert any("Legacy/local code" in w for w in r["data_quality"])


def test_conflicting_same_day_labs():
    assert st(res("P012"), "I3")["state"] == "CONFLICT"


def test_recency_resolves_timestamp_conflict():
    c = st(res("P011"), "I2")
    assert c["state"] == "TRUE" and "resolved_by_recency" in c["flags"]


def test_absence_never_hard_excludes_on_inclusion():
    p = dict(BY["P001"]); p["conditions"] = []; p["notes"] = [dict(id="X", date="2026-08-01", text="Seen for routine visit.")]
    c = st(match(p, TRIAL, AS_OF), "I2")
    assert c["state"] == "FALSE" and c["confidence"] < 0.8


def test_all_evidence_grounded():
    for p in PATS:
        r = match(p, TRIAL, AS_OF)
        assert r["grounding_failures"] == 0
        notes = {n["id"]: n["text"] for n in p["notes"]}
        for c in r["criteria"]:
            for e in c["evidence"]:
                if e["source"] == "note":
                    assert e["snippet"] in notes[e["ref"]]


def test_unparsed_criterion_blocks_eligibility():
    t = dict(TRIAL); t["criteria"] = TRIAL["criteria"] + [dict(id="I9", type="inclusion", kind="manual", text="Has a working smartphone")]
    assert match(BY["P001"], t, AS_OF)["decision"] == "NEEDS_REVIEW"


def test_phi_redaction():
    t, f = redact_phi("SSN 123-45-6789 call 555-123-4567 Mr. Rajesh Kumar")
    assert "123-45" not in t and set(f) >= {"SSN", "PHONE", "NAME"} and scan_phi(t) == {}


def test_criteria_text_parser():
    assert validate_criteria(TRIAL["criteria"]) == []
    kinds = [c["kind"] for c in TRIAL["criteria"]]
    assert kinds[:5] == ["age", "condition", "lab", "medication", "lab"] and TRIAL["criteria"][5].get("screening_only")
