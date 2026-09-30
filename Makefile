run:    ; python scripts/seed.py && uvicorn app.main:app --reload
test:   ; pytest -q
eval:   ; python -m app.evaluation
docker: ; docker compose up --build
