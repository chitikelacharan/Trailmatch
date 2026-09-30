"""Trial protocol handling: validates structured criteria and parses free-text
eligibility sections into structured criteria. Anything that cannot be parsed
becomes a 'manual' criterion -- it is NEVER silently dropped (patient-safety rule)."""
import re

from .terminology import CONDITIONS, MEDICATIONS, LABS

KINDS = {"age", "sex", "condition", "lab", "medication", "manual"}
OPS = {">=", "<=", ">", "<", "between", "=="}
SCREENING = re.compile(r"informed consent|willing (?:to|and)|able to (?:comply|understand|provide)|comply with", re.I)
_OP_MAP = {"≥": ">=", "≤": "<=", "at least": ">=", "at most": "<=", "greater than or equal to": ">=",
           "less than or equal to": "<=", "greater than": ">", "less than": "<", "above": ">", "below": "<"}
_OP_RX = r"(>=|<=|≥|≤|>|<|at least|at most|greater than or equal to|less than or equal to|greater than|less than|above|below|between)"


def _win(line):
    m = re.search(r"within\s+(?:the\s+)?(?:last|past|previous)?\s*(\d+)\s*(day|week|month|year)s?", line, re.I)
    if not m:
        return None
    n, u = int(m.group(1)), m.group(2).lower()
    return n * {"day": 1, "week": 7, "month": 30, "year": 365}[u]


def _find(line, table):
    low = line.lower()
    for key, spec in table.items():
        for s in sorted(spec["synonyms"], key=len, reverse=True):
            if re.search(rf"\b{re.escape(s.lower())}\b", low):
                return key
        for a in spec.get("abbrs", []):
            if re.search(rf"\b{re.escape(a)}\b", line):
                return key
    return None


def parse_line(line):
    if SCREENING.search(line):
        return dict(kind="manual", screening_only=True)
    m = re.search(r"\bage[d]?\b.*?(?:between\s*(\d+)\s*(?:and|-|to)\s*(\d+)|(?:>=|≥|at least)\s*(\d+)|(?:<=|≤|at most)\s*(\d+))", line, re.I) \
        or re.search(r"\b(\d+)\s*(?:-|to)\s*(\d+)\s*years", line, re.I)
    if m:
        g = m.groups()
        c = dict(kind="age")
        if g[1]:
            c.update(min=int(g[0]), max=int(g[1]))
        elif len(g) > 2 and g[2]:
            c["min"] = int(g[2])
        elif len(g) > 3 and g[3]:
            c["max"] = int(g[3])
        return c
    m = re.search(r"(\d+)\s*years?\s*(?:of age\s*)?(?:or|and)\s*(older|above|over)", line, re.I)
    if m:
        return dict(kind="age", min=int(m.group(1)))
    m = re.search(r"\b(?:sex|gender)\s*[:=]?\s*(female|male)\b|\b(female|male)\s+(?:patients?|participants?|subjects?)\b", line, re.I)
    if m:
        return dict(kind="sex", value=(m.group(1) or m.group(2)).lower())
    for key, spec in LABS.items():
        names = "|".join(re.escape(n) for n in sorted(spec["names"], key=len, reverse=True))
        m = re.search(rf"\b({names})\b\s*{_OP_RX}\s*(\d+(?:\.\d+)?)(?:\s*(?:and|-|to)\s*(\d+(?:\.\d+)?))?", line, re.I)
        if m:
            op = m.group(2).lower()
            op = _OP_MAP.get(op, op)
            c = dict(kind="lab", concept=key, op=op, value=float(m.group(3)))
            if op == "between" and m.group(4):
                c["value2"] = float(m.group(4))
            w = _win(line)
            if w:
                c["max_age_days"] = w
            return c
    key = _find(line, CONDITIONS)
    if key:
        c = dict(kind="condition", concept=key)
        w = _win(line)
        if w:
            c["lookback_days"] = w
        if re.search(r"\bactive\b|\bcurrent\b", line, re.I):
            c["active_only"] = True
        return c
    key = _find(line, MEDICATIONS)
    if key:
        c = dict(kind="medication", concept=key)
        w = _win(line)
        if w:
            c["within_days"] = w
        return c
    return dict(kind="manual")


def parse_criteria_text(text):
    section, crit, counters = None, [], {"inclusion": 0, "exclusion": 0}
    for raw in (text or "").splitlines():
        s = re.sub(r"^\s*(?:[-•*]|\d+[.)])\s*", "", raw).strip()
        if not s:
            continue
        low = s.lower()
        if low.startswith("inclusion criteria"):
            section = "inclusion"; continue
        if low.startswith("exclusion criteria"):
            section = "exclusion"; continue
        if section is None:
            continue
        counters[section] += 1
        c = parse_line(s)
        c.update(id=("I" if section == "inclusion" else "E") + str(counters[section]), type=section, text=s)
        crit.append(c)
    return crit


def validate_criteria(criteria):
    errs = []
    seen = set()
    for i, c in enumerate(criteria or []):
        cid = c.get("id") or f"C{i+1}"
        if cid in seen: errs.append(f"duplicate id {cid}")
        seen.add(cid)
        if c.get("type") not in ("inclusion", "exclusion"): errs.append(f"{cid}: type must be inclusion|exclusion")
        k = c.get("kind")
        if k not in KINDS: errs.append(f"{cid}: unknown kind {k}"); continue
        if k == "condition" and c.get("concept") not in CONDITIONS: errs.append(f"{cid}: unknown condition concept")
        if k == "medication" and c.get("concept") not in MEDICATIONS: errs.append(f"{cid}: unknown medication concept")
        if k == "lab":
            if c.get("concept") not in LABS: errs.append(f"{cid}: unknown lab concept")
            if c.get("op") not in OPS: errs.append(f"{cid}: bad op")
            if c.get("value") is None: errs.append(f"{cid}: lab needs value")
            if c.get("op") == "between" and c.get("value2") is None: errs.append(f"{cid}: between needs value2")
        if k == "sex" and c.get("value") not in ("male", "female"): errs.append(f"{cid}: sex value")
        if k == "age" and c.get("min") is None and c.get("max") is None: errs.append(f"{cid}: age needs min/max")
    return errs
