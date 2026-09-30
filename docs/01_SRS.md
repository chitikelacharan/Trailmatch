# Software Requirements Specification — TrialMatch (PNH2)

## 1. Purpose & scope
TrialMatch is a clinical-decision-support system that matches **de-identified** EHR data (structured + free-text notes)
against trial inclusion/exclusion criteria and returns an **explainable** decision, **evidence citations**, and an explicit list of
**missing evidence**. It never enrols a patient: every result requires human sign-off.

## 2. Stakeholders / users
| Role | Needs |
|---|---|
| Study coordinator | ranked candidate list, reasons, missing-data checklist, review workflow |
| Principal investigator | trust: evidence for every claim, low false-positive rate |
| Auditor / compliance | tamper-evident audit trail, accuracy metrics, no PHI access |
| Admin / DevOps | deployability, monitoring, secrets & key management |

## 3. Functional requirements
| ID | Requirement |
|---|---|
| FR-1 | Ingest patient bundles (demographics, conditions w/ ICD-10/ICD-9/local codes, labs w/ units & LOINC, medications, notes). |
| FR-2 | Scan every note for PHI patterns; redact by default, reject with `strict_deid=true`; report counts. |
| FR-3 | Accept trial criteria as structured JSON **or** free text ("Inclusion Criteria: … Exclusion Criteria: …"); parse to structured form; unparseable criteria become *manual* criteria (never dropped). |
| FR-4 | Evaluate each criterion to `TRUE / FALSE / UNKNOWN / CONFLICT` with confidence, rationale and verbatim evidence. |
| FR-5 | Patient decision `ELIGIBLE / NEEDS_REVIEW / INELIGIBLE` with `likely_ineligible` hint. |
| FR-6 | **Missing-evidence detection**: absent/stale labs, unknown DOB/sex, ambiguous mentions, unparsed criteria → concrete items + suggested source. |
| FR-7 | **Adversarial handling**: negation, family history, hedged language, ambiguous abbreviations (MI/MS/RA), conflicting notes/codes, miscoded diagnoses, legacy ICD-9 & local codes, unit conversion, implausible values, conflicting same-day labs, future-dated records, contradictory timestamps. |
| FR-8 | Batch-match all patients for a trial, ranked by decision & confidence. |
| FR-9 | Human review workflow (confirm / reject / request info) persisted with reviewer + note. |
| FR-10 | Evaluation endpoint/CLI on a gold set: accuracy, FP rate, unsafe errors, missing-evidence P/R, criterion accuracy, grounding failures. |
| FR-11 | Authentication, RBAC (admin / coordinator / auditor), audit log of every access and decision. |

## 4. Non-functional requirements
| ID | Requirement | Target |
|---|---|---|
| NFR-1 Safety | ineligible patient labelled ELIGIBLE | **0** on gold set (CI gate) |
| NFR-2 Grounding | every quoted snippet is a verbatim substring of source | 100 % |
| NFR-3 Privacy | PHI encrypted at rest (AES/Fernet), TLS in transit, no PHI in logs/metrics, minimum-necessary RBAC | HIPAA Safe-Harbor aligned |
| NFR-4 Performance | p95 single match | < 300 ms (rules engine), batch 1 000 patients < 60 s/replica |
| NFR-5 Scalability | stateless API, horizontal scale, shared cache/DB | 3→20 replicas via HPA |
| NFR-6 Availability | rolling deploys, PDB, health/readiness probes | 99.9 % |
| NFR-7 Auditability | hash-chained append-only audit log | tamper detection endpoint |
| NFR-8 Explainability | each decision traceable to criterion → evidence → source | always |

## 5. Decision semantics (safety contract)
* **INELIGIBLE** only when a criterion fails with confidence ≥ 0.8 (explicit, evidenced fail).
* **Absence of evidence never hard-excludes** a patient for an inclusion criterion (confidence 0.6 → `NEEDS_REVIEW`, `likely_ineligible=true`).
* **Conflicts are never auto-resolved**, except "newer documentation supersedes older" (flagged `resolved_by_recency`).
* **ELIGIBLE** requires *every* non-screening criterion resolved favourably with confidence ≥ 0.8. Unparsed criteria block ELIGIBLE.
* LLM output (optional) may only raise review flags; it cannot make a patient eligible or ineligible.

## 6. Assumptions & constraints
Input is already de-identified (dates shifted consistently); the terminology dictionary is a compact demo set and must be
replaced/extended (UMLS, SNOMED CT, RxNorm, LOINC) for real deployments; not a medical device — decision support only.

## 7. Acceptance criteria
`pytest` green (15 tests) · `python -m app.evaluation` gate passes · API flow test covers auth, RBAC, PHI redaction, matching, review, audit integrity.
