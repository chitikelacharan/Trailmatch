# Security & Privacy Controls

| Area | Control | Where |
|---|---|---|
| AuthN | JWT (HS256, 60-min TTL), PBKDF2-SHA256 (200k iters), login rate-limit | `security.py` |
| AuthZ | RBAC: coordinator/admin handle PHI; auditor sees audit + metrics only | `require()` |
| Encryption at rest | Patient records and match results Fernet(AES-128-CBC+HMAC) encrypted; key from secret manager (`DATA_KEY`) | `db.py` |
| Encryption in transit | TLS at ingress (cert-manager), HSTS header | `k8s/`, `main.py` |
| De-identification | PHI regex scan (SSN, phone, e-mail, MRN, names, ZIP+4, URL, IP) → redact or reject | `nlp.py` |
| Audit | Append-only, hash-chained log of every login, view, ingest, match, review; `/audit` verifies integrity | `db.py` |
| No PHI in telemetry | Metrics carry counts only; audit `detail` stores decisions, never text | `metrics.py` |
| Hallucination defence | Verbatim-quote grounding check on every evidence snippet; LLM output flag-only | `engine.py`, `llm.py` |
| Hardening | non-root container, read-only FS, dropped capabilities, NetworkPolicy, security headers, secrets via K8s Secret | `Dockerfile`, `k8s/` |
| Fail-closed config | production refuses to start without `JWT_SECRET` / `DATA_KEY` | `config.py` |

**Compliance mapping (HIPAA Security Rule):** access control §164.312(a), audit controls §164.312(b), integrity §164.312(c),
transmission security §164.312(e). Add for real deployment: BAA with cloud vendor, key rotation (KMS), SSO/MFA, DPIA, IRB approval.
