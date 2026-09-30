"""OPTIONAL LLM assist (off by default: LLM_ENABLED=0).

Safety design against hallucination:
  * The LLM may only return VERBATIM quotes; every quote is verified as a substring of the source note.
  * LLM-derived evidence is tagged source='llm' and can only ever produce 'uncertain' evidence,
    i.e. it can raise a human-review flag but can never make a patient ELIGIBLE or INELIGIBLE.
  * Only de-identified, redacted text is ever sent.
"""
import json
import urllib.request

from . import config


def assist(notes, display):
    if not (config.LLM_ENABLED and config.ANTHROPIC_API_KEY):
        return []
    out = []
    for n in notes or []:
        prompt = (f"From the clinical note, return JSON list of verbatim sentences that state or suggest the patient "
                  f"has '{display}'. Copy sentences EXACTLY. Return [] if none. JSON only.\n\nNOTE:\n{n['text'][:6000]}")
        body = json.dumps({"model": config.LLM_MODEL, "max_tokens": 500,
                           "messages": [{"role": "user", "content": prompt}]}).encode()
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", body, {
            "content-type": "application/json", "x-api-key": config.ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                txt = json.loads(r.read())["content"][0]["text"]
            quotes = json.loads(txt.strip().strip("`").removeprefix("json").strip())
        except Exception:
            continue
        for q in quotes if isinstance(quotes, list) else []:
            if isinstance(q, str) and q and q in n["text"]:            # grounding verification
                out.append(dict(source="llm", ref=n["id"], date=n.get("date"), snippet=q, polarity="uncertain"))
    return out
