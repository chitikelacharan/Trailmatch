# 🧪 TrialMatch — Explainable Clinical Trial Eligibility Matcher (PNH2)

AI-assisted matching of **de-identified EHR records** against **complex trial criteria**, with evidence-backed
inclusion/exclusion reasoning, **missing-evidence detection**, adversarial resilience and a measurable safety gate.

## Quick start
```bash
pip install -r requirements-dev.txt
python scripts/seed.py && uvicorn app.main:app --reload     # UI: http://localhost:8000   API docs: /docs
pytest -q                                                    # 15 tests
python -m app.evaluation                                     # gold-set metrics + safety gate
```
Dev logins: `coordinator / Coord#12345`, `auditor / Audit#12345`, `admin / Admin#12345`
(in production, set `ENV=production` and provide secrets — see `.env.example`).
In the UI click **Load sample data → Match all patients → click a row** to see reasoning.

## What maps to which level
| Level | Deliverable | Location |
|---|---|---|
| **1** Idea/Architecture/Planning | SRS, architecture + data-flow diagrams, wireframes, tech stack, roadmap | `docs/01…03`, this README |
| **2** Core MVP | schemas, business logic, REST APIs, working UI | `app/db.py`, `engine.py`, `main.py`, `static/` |
| **3** Intelligence/Security/Deployment | NLP + adversarial logic, optional grounded LLM, JWT/RBAC/encryption/audit, CI/CD, cloud deploy | `nlp.py`, `security.py`, `llm.py`, `.github/`, `docs/04–05` |
| **4** Scale/Reliability | Docker, K8s + HPA + PDB, Redis cache, Postgres, Prometheus alerts | `Dockerfile`, `k8s/`, `monitoring/`, `cache.py` |

## Adversarial cases covered (and tested)
| Edge case | Sample | Behaviour |
|---|---|---|
| Negation / family history | P005 | "No history of MI", "Mother had heart failure" ignored → ELIGIBLE |
| Ambiguous abbreviation ("MI") | P006 | no cardiac context → UNKNOWN + clarification request |
| Miscoded diagnosis | P004 | code E11 vs note "type 1 diabetes" → CONFLICT → review |
| Legacy ICD-9 / local code / mmol/mol units | P007 | mapped + converted, data-quality warning |
| Contradictory timestamps | P011 | newer diagnosis supersedes older denial (flagged) |
| Conflicting same-day labs | P012 | CONFLICT, repeat lab requested |
| Missing / stale labs | P003 | exact missing-evidence list (HbA1c, eGFR) |
| PHI leakage | P010 | SSN / phone / name redacted at ingestion |
| Hallucination | all | every quote verified as verbatim substring; LLM flag-only |

## Evaluation (gold set of 12)
Decision accuracy 100 % · ineligible→ELIGIBLE errors **0** · false-positive rate **0** · missing-evidence P/R 1.0 · grounding failures 0.
*Small synthetic set — treat as a harness demonstration; extend `data/gold_labels.json` with clinician-adjudicated cases.*

## Roadmap
1. **Now (MVP):** rules-first engine, 6 criterion kinds, sample protocol. 2. **Next:** SNOMED/UMLS/RxNorm services, FHIR R4 ingest,
temporal criteria ("2 prior lines of therapy"), OR/AND groups & nested logic. 3. **Then:** clinician-in-the-loop active learning,
calibrated confidence, bias/fairness audits, SSO/MFA, multi-tenant protocol library. 4. **Later:** prospective validation, SaMD assessment.

## Limitations (honest)
Demo terminology (11 conditions, 6 meds, 6 labs) · English notes only · regex NLP (swap for clinical NER e.g. medspaCy/scispaCy) ·
flat AND-logic across criteria · not a medical device; a human must sign off every decision.
