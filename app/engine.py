"""Explainable eligibility matching engine.

Every criterion evaluates to a TRI-STATE+ value about the criterion *statement*:
    TRUE | FALSE | UNKNOWN | CONFLICT
with evidence (verbatim snippets / structured rows), a confidence, a plain-English rationale,
and explicit missing-evidence requests. Patient-level decision:

    INELIGIBLE   any inclusion FALSE / exclusion TRUE with confidence >= 0.8 (hard, evidenced failure)
    NEEDS_REVIEW something unresolved: UNKNOWN, CONFLICT, low confidence, or absence-based failure
    ELIGIBLE     every non-screening criterion resolved in the patient's favour with confidence >= 0.8

Safety rules: absence of evidence never disqualifies on its own; conflicts are never auto-resolved
(except strictly newer-supersedes-older); unparsed criteria block ELIGIBLE; every quoted snippet is
verified to exist verbatim in the source (grounding check); the system never enrols -- a human signs off.
"""
from datetime import date

from . import llm
from .nlp import find_mentions, extract_labs
from .terminology import (CONDITIONS, MEDICATIONS, LABS, KNOWN_CODE_SYSTEMS, code_concepts,
                          convert_lab)

ENGINE_VERSION = "1.0.0"
HARD = 0.8


def d(s):
    if not s:
        return None
    if isinstance(s, date):
        return s
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def _age(p, as_of):
    b = d((p.get("demographics") or {}).get("birth_date"))
    if not b:
        return None
    return as_of.year - b.year - ((as_of.month, as_of.day) < (b.month, b.day))


def _complete(p):
    return bool(p.get("notes")) and bool(p.get("conditions") or p.get("labs") or p.get("medications"))


def _res(state, conf, evidence, rationale, missing=None, flags=None):
    return dict(state=state, confidence=round(conf, 2), evidence=evidence, rationale=rationale,
                missing=missing or [], flags=flags or [])


def _miss(item, why, source):
    return dict(item=item, why=why, suggested_source=source)


def _quote(e):
    return f"{e['source']}:{e.get('ref')}" + (f" ({e['date']})" if e.get("date") else "")


# --------------------------------------------------------------------------- code mapping
def map_condition(cond):
    """Concepts for a structured condition; falls back to display-text mapping for
    undocumented / legacy local codes."""
    cs = code_concepts(cond.get("code"), cond.get("system"))
    if cs:
        return cs
    disp = cond.get("display") or ""
    out = set()
    for k, spec in CONDITIONS.items():
        for m in find_mentions(disp, dict(spec, generic=[]), k):
            if m["cls"] == "positive":
                out.add(k)
    return out


def data_quality(p, as_of):
    w = []
    for c in p.get("conditions") or []:
        if not code_concepts(c.get("code"), c.get("system")):
            if map_condition(c):
                w.append(f"Legacy/local code '{c.get('code')}' ({c.get('system') or 'unknown system'}) mapped via display text "
                         f"'{c.get('display')}' - verify mapping.")
            elif (c.get("system") or "").lower() not in KNOWN_CODE_SYSTEMS or not c.get("code"):
                w.append(f"Unmapped code '{c.get('code')}' ({c.get('display')}) could not be linked to a known concept.")
        if d(c.get("onset")) and d(c.get("onset")) > as_of:
            w.append(f"Future-dated onset for '{c.get('display')}' ({c.get('onset')}) ignored.")
    for l in p.get("labs") or []:
        if d(l.get("date")) and d(l.get("date")) > as_of:
            w.append(f"Future-dated lab '{l.get('name')}' ({l.get('date')}) ignored.")
    if not (p.get("demographics") or {}).get("birth_date"):
        w.append("Missing date of birth.")
    if not p.get("notes"):
        w.append("No clinical notes available; note-based evidence cannot be assessed.")
    return w


# --------------------------------------------------------------------------- presence evaluators
def _collect_condition(p, key, crit, as_of):
    out = dict(pos=[], neg=[], unc=[], amb=[], fam=[], outside=[])
    spec = CONDITIONS[key]
    for c in p.get("conditions") or []:
        if key not in map_condition(c):
            continue
        status = (c.get("status") or "active").lower()
        if status in ("entered-in-error", "refuted"):
            continue
        onset = d(c.get("onset"))
        ev = dict(source="structured", ref=c.get("code"), date=c.get("onset"),
                  snippet=f"{c.get('code')} {c.get('display')} (status: {status})", polarity="positive")
        if onset and onset > as_of:
            continue
        if crit.get("lookback_days") and onset and (as_of - onset).days > crit["lookback_days"]:
            out["outside"].append(ev); continue
        if crit.get("active_only") and status in ("resolved", "inactive"):
            out["outside"].append(ev); continue
        out["pos"].append(ev)
    bucket = dict(positive="pos", negated="neg", uncertain="unc", ambiguous="amb", family="fam")
    for n in p.get("notes") or []:
        for m in find_mentions(n.get("text", ""), spec, key):
            out[bucket[m["cls"]]].append(dict(source="note", ref=n.get("id"), date=n.get("date"),
                                              snippet=m["sentence"], polarity=m["cls"]))
    return out


def _collect_med(p, key, crit, as_of):
    out = dict(pos=[], neg=[], unc=[], amb=[], fam=[], outside=[])
    spec = MEDICATIONS[key]
    within = crit.get("within_days")
    for m in p.get("medications") or []:
        nm = (m.get("name") or "")
        if not find_mentions(nm, spec, key):
            continue
        start, end = d(m.get("start")), d(m.get("end"))
        active = (end is None or end >= as_of) and (m.get("status") or "active").lower() not in ("stopped", "completed")
        ev = dict(source="structured", ref=nm, date=m.get("start"),
                  snippet=f"{nm} start={m.get('start')} end={m.get('end')}", polarity="positive")
        recent = within and end and (as_of - end).days <= within
        if active or recent:
            out["pos"].append(ev)
        else:
            ev["polarity"] = "negated"; ev["snippet"] += " (not active in window)"
            out["neg"].append(ev)
    bucket = dict(positive="pos", negated="neg", uncertain="unc", ambiguous="amb", family="fam")
    for n in p.get("notes") or []:
        for m in find_mentions(n.get("text", ""), spec, key):
            out[bucket[m["cls"]]].append(dict(source="note", ref=n.get("id"), date=n.get("date"),
                                              snippet=m["sentence"], polarity=m["cls"]))
    return out


def _decide_presence(p, crit, display, ev, rival_flag, as_of, what):
    pos, neg, unc, amb = ev["pos"], ev["neg"], ev["unc"], ev["amb"]
    spos = [e for e in pos if e["source"] == "structured"]
    all_ev = pos + neg + unc + amb
    if rival_flag:
        return _res("CONFLICT", 0.3, all_ev + rival_flag["evidence"],
                    f"Possible miscoding: {rival_flag['msg']}",
                    [_miss(f"Clinician-confirmed {display} type/status", "structured codes and notes disagree",
                           "treating physician / problem-list reconciliation")], ["possible_miscoding"])
    if pos and neg:
        pd_, nd_ = [d(e["date"]) for e in pos], [d(e["date"]) for e in neg]
        if all(pd_) and all(nd_) and min(pd_) > max(nd_):
            return _res("TRUE", 0.8, pos + neg,
                        f"{display} was documented as absent earlier ({max(nd_)}) but documented present later "
                        f"({min(pd_)}); the newer documentation supersedes.", flags=["resolved_by_recency"])
        return _res("CONFLICT", 0.3, pos + neg,
                    f"Contradictory documentation for {display}: present per {_quote(pos[0])} but absent per {_quote(neg[0])}.",
                    [_miss(f"Reconciled {display} status", "contradictory records with non-resolvable timestamps",
                           "clinician review of source notes")], ["contradiction"])
    if pos:
        conf = 0.95 if spos else 0.85
        return _res("TRUE", conf, pos, f"{display} is documented ({_quote(pos[0])}).")
    if neg:
        return _res("FALSE", 0.9, neg, f"{display} is explicitly documented as absent/not current ({_quote(neg[0])}).")
    if unc or amb:
        kind = "ambiguous abbreviation" if amb and not unc else "uncertain/unspecified mention"
        item = f"Clarification of {kind} for {display}"
        return _res("UNKNOWN", 0.4, unc + amb,
                    f"Only {kind} found for {display}; cannot be treated as confirmed.",
                    [_miss(item, "mention is hedged, unspecified, or uses an ambiguous abbreviation",
                           "clinician note clarification / confirmatory test")],
                    ["ambiguous_abbreviation" if amb else "uncertain_mention"])
    if ev.get("outside"):
        o = ev["outside"][0]
        return _res("FALSE", 0.9, ev["outside"],
                    f"{display} recorded ({_quote(o)}) but outside the criterion window/status requirement.")
    if not _complete(p):
        return _res("UNKNOWN", 0.3, [], f"No evidence of {display}, and the record is too sparse to infer absence.",
                    [_miss(f"Documentation of {display} status", "record incomplete", "problem list / recent clinic note")],
                    ["sparse_record"])
    conf = 0.85 if crit["type"] == "exclusion" else 0.6
    if what == "llm":
        pass
    return _res("FALSE", conf, [], f"No evidence of {display} found in {len(p.get('notes') or [])} note(s) or structured data "
                                   f"(absence-based).", flags=["absence_of_evidence"])


def eval_condition(p, crit, as_of):
    key = crit["concept"]; spec = CONDITIONS[key]
    ev = _collect_condition(p, key, crit, as_of)
    if not (ev["pos"] or ev["neg"] or ev["unc"] or ev["amb"]) and llm.config.LLM_ENABLED:
        ev["unc"] += llm.assist(p.get("notes"), spec["display"])
    rival = None
    for r in spec.get("conflicts_with", []):
        rev = _collect_condition(p, r, {}, as_of)
        r_note = [e for e in rev["pos"] if e["source"] == "note"]
        r_struct = [e for e in rev["pos"] if e["source"] == "structured"]
        spos = [e for e in ev["pos"] if e["source"] == "structured"]
        npos = [e for e in ev["pos"] if e["source"] == "note"]
        if spos and not npos and r_note:
            rival = dict(evidence=r_note, msg=f"structured code says {spec['display']} but notes state "
                                              f"{CONDITIONS[r]['display']} ({_quote(r_note[0])}).")
        elif npos and not spos and r_struct:
            rival = dict(evidence=r_struct, msg=f"notes say {spec['display']} but structured data codes "
                                                f"{CONDITIONS[r]['display']} ({_quote(r_struct[0])}).")
    return _decide_presence(p, crit, spec["display"], ev, rival, as_of, "cond")


def eval_medication(p, crit, as_of):
    key = crit["concept"]; spec = MEDICATIONS[key]
    return _decide_presence(p, crit, spec["display"], _collect_med(p, key, crit, as_of), None, as_of, "med")


# --------------------------------------------------------------------------- age / sex
def eval_age(p, crit, as_of):
    a = _age(p, as_of)
    if a is None:
        return _res("UNKNOWN", 0.0, [], "Date of birth missing.",
                    [_miss("Date of birth", "needed to compute age", "registration / demographics")])
    lo, hi = crit.get("min"), crit.get("max")
    ok = (lo is None or a >= lo) and (hi is None or a <= hi)
    ev = [dict(source="structured", ref="birth_date", date=p["demographics"]["birth_date"],
               snippet=f"birth_date={p['demographics']['birth_date']} -> age {a} on {as_of}", polarity="positive")]
    return _res("TRUE" if ok else "FALSE", 1.0, ev,
                f"Age {a} is {'within' if ok else 'outside'} required range [{lo if lo is not None else '-'}, {hi if hi is not None else '-'}].")


def eval_sex(p, crit, as_of):
    s = ((p.get("demographics") or {}).get("sex") or "").lower()
    if not s:
        return _res("UNKNOWN", 0.0, [], "Sex not recorded.", [_miss("Sex", "needed for sex-specific criterion", "demographics")])
    ok = s == crit["value"]
    return _res("TRUE" if ok else "FALSE", 1.0, [dict(source="structured", ref="sex", date=None, snippet=f"sex={s}", polarity="positive")],
                f"Recorded sex '{s}' {'matches' if ok else 'does not match'} '{crit['value']}'.")


# --------------------------------------------------------------------------- labs
def _cmp(op, v, a, b=None):
    return {">=": v >= a, "<=": v <= a, ">": v > a, "<": v < a, "==": v == a,
            "between": b is not None and a <= v <= b}[op]


def _lab_candidates(p, key, as_of, flags):
    spec = LABS[key]; c = []
    for l in p.get("labs") or []:
        if not (l.get("name") or l.get("loinc")):
            continue
        from .terminology import lab_matches
        if not lab_matches(key, l):
            continue
        dt = d(l.get("date"))
        if dt and dt > as_of:
            continue
        try:
            v, assumed = convert_lab(key, l["value"], l.get("unit"))
        except (ValueError, TypeError, KeyError):
            flags.append(f"Unparseable {spec['display']} value/unit in structured lab ({l.get('value')} {l.get('unit')}).")
            continue
        c.append(dict(v=v, date=dt, src="structured", assumed=assumed, ref=l.get("name"),
                      snippet=f"{l.get('name')} {l.get('value')} {l.get('unit') or ''} on {l.get('date')}".replace("  ", " ")))
    for n in p.get("notes") or []:
        nd = d(n.get("date"))
        if nd and nd > as_of:
            continue
        for x in extract_labs(n.get("text", ""), n.get("date")):
            if x["lab"] != key:
                continue
            try:
                v, assumed = convert_lab(key, x["value"], x["unit"])
            except ValueError:
                continue
            c.append(dict(v=v, date=nd, src="note", assumed=assumed, ref=n.get("id"), snippet=x["sentence"]))
    return c


def eval_lab(p, crit, as_of):
    key = crit["concept"]; spec = LABS[key]; flags = []
    cands = _lab_candidates(p, key, as_of, flags)
    maxage = crit.get("max_age_days")
    win = f" within {maxage} days" if maxage else ""
    need = _miss(f"{spec['display']} result{win}", f"required to evaluate '{crit.get('text', spec['display'])}'",
                 "laboratory results / recent clinic note")
    if not cands:
        return _res("UNKNOWN", 0.0, [], f"No {spec['display']} result found.", [need], ["missing_lab"] + flags)
    lo, hi = spec["plausible"]
    bad = [c for c in cands if not (lo <= c["v"] <= hi)]
    cands = [c for c in cands if lo <= c["v"] <= hi]
    if not cands:
        return _res("UNKNOWN", 0.0, [], f"All {spec['display']} values are physiologically implausible (possible entry/unit error).",
                    [need], ["implausible_value"])
    dated = [c for c in cands if c["date"]]
    if maxage:
        recent = [c for c in dated if (as_of - c["date"]).days <= maxage]
        if not recent:
            latest = max(dated, key=lambda c: c["date"]) if dated else cands[0]
            age_txt = f"{(as_of - latest['date']).days} days old" if latest["date"] else "undated"
            need["why"] += f"; latest available is {age_txt} ({latest['v']:.4g} {spec['unit']})"
            return _res("UNKNOWN", 0.2, [_ev_lab(latest)], f"No {spec['display']} within {maxage} days (latest is {age_txt}).",
                        [need], ["stale_lab"] + flags)
        pool = recent
    else:
        pool = dated or cands
    latest_date = max((c["date"] for c in pool if c["date"]), default=None)
    latest = [c for c in pool if c["date"] == latest_date] if latest_date else pool
    vals = [c["v"] for c in latest]
    if len(vals) > 1 and (max(vals) - min(vals)) / max(max(vals), 1e-9) > 0.10 and not all(c["assumed"] for c in latest):
        return _res("CONFLICT", 0.3, [_ev_lab(c) for c in latest],
                    f"Multiple {spec['display']} values on {latest_date} disagree ({', '.join(f'{v:.4g}' for v in vals)}).",
                    [_miss(f"Repeat/verified {spec['display']}", "same-day results disagree", "laboratory verification")],
                    ["conflicting_values"])
    best = sorted(latest, key=lambda c: (c["src"] != "structured"))[0]
    ok = _cmp(crit["op"], best["v"], crit["value"], crit.get("value2"))
    conf = 0.98 if best["src"] == "structured" and not best["assumed"] else 0.9 if not best["assumed"] else 0.7
    fl = list(flags)
    if best["assumed"]:
        fl.append("unit_assumed")
    if best["src"] == "note":
        fl.append("value_from_free_text")
    target = f"{crit['op']} {crit['value']}" + (f"–{crit['value2']}" if crit["op"] == "between" else "")
    return _res("TRUE" if ok else "FALSE", conf, [_ev_lab(best)],
                f"{spec['display']} {best['v']:.4g} {spec['unit']} ({best['date']}) {'satisfies' if ok else 'does not satisfy'} "
                f"'{target} {spec['unit']}'.", flags=fl)


def _ev_lab(c):
    return dict(source=c["src"], ref=c["ref"], date=str(c["date"]) if c["date"] else None, snippet=c["snippet"], polarity="positive")


def eval_manual(p, crit, as_of):
    return _res("UNKNOWN", 0.0, [], "Criterion could not be machine-interpreted; requires manual review.",
                [_miss(f"Manual review: {crit.get('text', crit['id'])}", "unparsed / non-structured criterion", "study coordinator")],
                ["unparsed_criterion"])


EVALUATORS = dict(age=eval_age, sex=eval_sex, condition=eval_condition, lab=eval_lab,
                  medication=eval_medication, manual=eval_manual)


# --------------------------------------------------------------------------- grounding check
def grounding_check(p, results):
    notes = {n.get("id"): n.get("text", "") for n in p.get("notes") or []}
    failed = 0
    for r in results:
        keep = []
        for e in r["evidence"]:
            if e["source"] in ("note", "llm"):
                if e["snippet"] and e["snippet"] in notes.get(e["ref"], ""):
                    keep.append(e)
                else:
                    failed += 1
            else:
                keep.append(e)
        if len(keep) != len(r["evidence"]):
            r["evidence"] = keep
            r["state"], r["confidence"] = "UNKNOWN", 0.0
            r["flags"].append("grounding_failed")
    return failed


# --------------------------------------------------------------------------- aggregation
def match(patient, trial, as_of=None):
    as_of = as_of or date.today()
    results = []
    for c in trial["criteria"]:
        r = EVALUATORS[c["kind"]](patient, c, as_of)
        r.update(id=c["id"], type=c["type"], text=c.get("text", c["id"]), kind=c["kind"],
                 screening_only=bool(c.get("screening_only")))
        results.append(r)
    ungrounded = grounding_check(patient, results)

    hard, soft, unresolved, screening = [], [], [], []
    for r in results:
        if r["screening_only"]:
            screening.append(r); continue
        fail = (r["type"] == "inclusion" and r["state"] == "FALSE") or (r["type"] == "exclusion" and r["state"] == "TRUE")
        if fail:
            (hard if r["confidence"] >= HARD else soft).append(r)
        elif r["state"] in ("UNKNOWN", "CONFLICT") or r["confidence"] < HARD:
            unresolved.append(r)

    likely = bool(soft)
    if hard:
        decision = "INELIGIBLE"
    elif soft or unresolved:
        decision = "NEEDS_REVIEW"
    else:
        decision = "ELIGIBLE"

    missing, seen = [], set()
    for r in hard + soft + unresolved:
        for m in r["missing"]:
            k = (m["item"],)
            if k not in seen:
                seen.add(k); missing.append(dict(m, criterion_id=r["id"]))
    considered = [r for r in results if not r["screening_only"]]
    satisfied = sum(1 for r in considered if r not in hard + soft + unresolved)
    conf = min([r["confidence"] for r in considered] or [0.0])
    return dict(
        patient_id=patient.get("id"), trial_id=trial.get("id"), decision=decision, likely_ineligible=likely,
        confidence=round(conf, 2), criteria_satisfied=f"{satisfied}/{len(considered)}",
        summary=_summary(decision, hard, soft, unresolved, screening),
        criteria=results, missing_evidence=missing, data_quality=data_quality(patient, as_of),
        screening_only=[dict(id=r["id"], text=r["text"]) for r in screening],
        grounding_failures=ungrounded, engine_version=ENGINE_VERSION, as_of=str(as_of),
        requires_human_signoff=True)


def _summary(decision, hard, soft, unresolved, screening):
    if decision == "INELIGIBLE":
        return "Ineligible: " + "; ".join(f"[{r['id']}] {r['rationale']}" for r in hard)
    if decision == "NEEDS_REVIEW":
        parts = [f"[{r['id']}] {r['rationale']}" for r in soft + unresolved]
        pre = "Likely ineligible but not conclusive. " if soft else "Cannot finalize eligibility. "
        return pre + "; ".join(parts)
    tail = f" Verify at screening: {', '.join(r['text'] for r in screening)}." if screening else ""
    return "All criteria resolved in the patient's favour with high confidence; pending human sign-off." + tail
