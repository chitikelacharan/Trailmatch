"""Clinical-note NLP: sentence split, mention finding, negation / family / uncertainty
scoping, ambiguous-abbreviation handling, lab extraction, and PHI (de-id) scanning.
All extractions return VERBATIM sentence text so every claim can be grounding-checked."""
import re
from functools import lru_cache

from .terminology import LABS

SENT_SPLIT = re.compile(r"(?<=[.!?;\n])\s+")
NEG = re.compile(r"\b(no|denies|denied|without|negative for|free of|absence of|no evidence of|no history of|"
                 r"never had|never|not (?:have|had|diagnosed with|taking|on|using)|stopped|discontinued|"
                 r"no longer (?:taking|on)|(?:is|was|are|were) not)\b")
FAMILY = re.compile(r"\b(family history|fhx|fh|mother|father|sibling|brother|sister|grandmother|grandfather|"
                    r"aunt|uncle|parents?)\b")
UNCERTAIN = re.compile(r"\b(possible|probable|suspected|suspicion|rule out|r/o|questionable|concern for|"
                       r"cannot exclude|likely|\?)")
POST_NEG = re.compile(r"^\W*(?:was |is |were )?(?:ruled out|not present|absent|negative|excluded|resolved)")
CONTRAST = re.compile(r"\b(but|however|although|except)\b|;")


def sentences(text):
    return [s.strip() for s in SENT_SPLIT.split(text or "") if s.strip()]


@lru_cache(maxsize=256)
def _compile(spec_key, synonyms, abbrs, generic, amb):
    pats = []
    for s in sorted(synonyms, key=len, reverse=True):
        pats.append(("specific", re.compile(rf"\b{re.escape(s)}\b", re.I)))
    for a in abbrs:
        pats.append(("specific", re.compile(rf"\b{re.escape(a)}\b")))          # case-sensitive
    for g in sorted(generic, key=len, reverse=True):
        # generic 'diabetes' must NOT match when a type qualifier is adjacent
        pats.append(("generic", re.compile(
            rf"(?<!type 1 )(?<!type 2 )(?<!type i )(?<!type ii )(?<!gestational )\b{re.escape(g)}\b"
            rf"(?!\s*(?:mellitus\s*)?type\s*(?:1|2|i|ii)\b)", re.I)))
    for a in amb:
        pats.append(("ambiguous", re.compile(rf"\b{re.escape(a)}\b")))
    return pats


def _scope(sentence, start, end):
    prefix = sentence[:start].lower()
    prefix = CONTRAST.split(prefix)[-1][-70:]
    suffix = sentence[end:].lower()
    if FAMILY.search(prefix):
        return "family"
    if NEG.search(prefix) or POST_NEG.match(suffix):
        return "negated"
    if UNCERTAIN.search(prefix) or UNCERTAIN.search(suffix[:25]):
        return "uncertain"
    return "positive"


def find_mentions(text, spec, spec_key):
    """Yield dicts: {sentence, cls, kind, matched}. cls in positive|negated|family|uncertain|ambiguous."""
    pats = _compile(spec_key, tuple(spec["synonyms"]), tuple(spec.get("abbrs", [])),
                    tuple(spec.get("generic", [])), tuple((spec.get("ambiguous") or {}).keys()))
    lowered = (text or "").lower()
    out = []
    for sent in sentences(text):
        taken = []
        for kind, pat in pats:
            for m in pat.finditer(sent):
                if any(m.start() < e and m.end() > s for s, e in taken):
                    continue
                taken.append((m.start(), m.end()))
                cls = _scope(sent, m.start(), m.end())
                if kind == "generic" and cls == "positive":
                    cls = "uncertain"                       # e.g. 'diabetes' with unspecified type
                if kind == "ambiguous":
                    cues = spec["ambiguous"][m.group(0)]
                    if cls in ("positive", "uncertain"):
                        cls = "positive" if any(c in lowered for c in cues) else "ambiguous"
                out.append(dict(sentence=sent, cls=cls, kind=kind, matched=m.group(0)))
    return out


def extract_labs(text, note_date=None):
    """Regex lab extraction from free text: 'HbA1c 8.2%', 'eGFR was 45 mL/min/1.73m2' ..."""
    found = []
    for key, spec in LABS.items():
        names = "|".join(re.escape(n) for n in sorted(spec["names"], key=len, reverse=True))
        rx = re.compile(rf"\b(?P<name>{names})\b\s*(?:level|result)?\s*(?:of|was|is|=|:)?\s*"
                        rf"(?P<val>\d+(?:\.\d+)?)\s*(?P<unit>%|mg/dl|mmol/l|mmol/mol|umol/l|µmol/l|u/l|"
                        rf"ml/min/1\.73\s?m2|ml/min|kg/m2)?", re.I)
        for sent in sentences(text):
            for m in rx.finditer(sent):
                found.append(dict(lab=key, value=float(m.group("val")), unit=m.group("unit"),
                                  sentence=sent, date=note_date))
    return found


# ----------------------------------------------------------------------------- de-identification
PHI_PATTERNS = {
    "SSN": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "PHONE": re.compile(r"\b(?:\+?1[-. ]?)?\(?\d{3}\)?[-. ]\d{3}[-. ]\d{4}\b"),
    "EMAIL": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"),
    "MRN": re.compile(r"\b(?:MRN|Medical Record Number)[:#\s]*\d{4,}\b", re.I),
    "NAME": re.compile(r"\b(?:Mr|Mrs|Ms|Dr|Patient name)\.?[:\s]+[A-Z][a-z]+(?:\s[A-Z][a-z]+)?"),
    "ZIP": re.compile(r"\b\d{5}-\d{4}\b"),
    "URL": re.compile(r"https?://\S+"),
    "IP": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
}


def scan_phi(text):
    return {k: len(p.findall(text or "")) for k, p in PHI_PATTERNS.items() if p.search(text or "")}


def redact_phi(text):
    findings = {}
    for k, p in PHI_PATTERNS.items():
        text, n = p.subn(f"[REDACTED_{k}]", text or "")
        if n:
            findings[k] = n
    return text, findings
