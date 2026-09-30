# Deployment Guide

## Local
```bash
pip install -r requirements-dev.txt
python scripts/seed.py            # 12 synthetic patients + DIAB-201 protocol
uvicorn app.main:app --reload     # http://localhost:8000  (UI)  /docs (OpenAPI)
# logins (dev only): coordinator/Coord#12345  auditor/Audit#12345  admin/Admin#12345
```
## Docker Compose (Postgres + Redis + Prometheus + Grafana)
```bash
export JWT_SECRET=$(python -c "import secrets;print(secrets.token_urlsafe(48))")
export DATA_KEY=$(python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())")
export ADMIN_PASSWORD=... COORDINATOR_PASSWORD=... AUDITOR_PASSWORD=...
docker compose up --build         # API :8000  Prometheus :9090  Grafana :3000
```
## Public cloud (pick one)
* **Render / Railway / Fly.io (fastest public URL):** connect the GitHub repo, use the Dockerfile, add a managed PostgreSQL + Redis,
  set env vars from `.env.example`. HTTPS is automatic.
* **Google Cloud Run + Cloud SQL:** `gcloud run deploy trialmatch --source . --set-env-vars ...` (secrets from Secret Manager).
* **Kubernetes (EKS/GKE/AKS):** `kubectl apply -f k8s/deployment.yaml` after creating secret
  `kubectl -n trialmatch create secret generic trialmatch-secrets --from-env-file=.env`.
  HPA scales 3→20 pods at 65 % CPU; PDB keeps ≥2 pods during node drains.
## CI/CD
`.github/workflows/ci-cd.yml`: tests → **safety evaluation gate** → Docker build/push (GHCR) → Trivy scan → `kubectl set image` rolling deploy.
## Monitoring
`/metrics` exposes request rate/latency, decision counts, cache hit/miss, login failures, evaluation metrics.
`monitoring/alerts.yml`: error rate, p95 latency, login spikes, **safety-regression alert**, review backlog.
Suggested Grafana panels: decisions by class, cache hit ratio, p95 `match_seconds`, 5xx rate.
## Performance
Deterministic engine (~ms per patient); results cached by content hash in Redis; horizontal scale is stateless.
Load test example: `hey -n 2000 -c 50 -m POST -H "Authorization: Bearer $T" -d '{"patient_id":"P001","trial_id":"DIAB-201"}' $URL/match`.
