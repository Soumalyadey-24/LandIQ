# LandIQ — common tasks
.PHONY: help setup backend frontend dev seed reset test docker docker-down clean \
        htr-setup htr-test htr-eval htr-models

help:
	@echo "LandIQ"
	@echo "  make setup       Install backend and frontend dependencies"
	@echo "  make dev         Run backend (8000) and frontend (5173) together"
	@echo "  make backend     Run the API only"
	@echo "  make frontend    Run the web app only"
	@echo "  make seed        Create the schema and load the demo dataset"
	@echo "  make reset       Wipe and reload the demo dataset"
	@echo "  make test        Run the end-to-end hero flow test"
	@echo "  make htr-setup   Install the AI stack + download HTR weights (~1.3 GB)"
	@echo "  make htr-test    Run the HTR smoke tests"
	@echo "  make htr-eval    Regenerate the published CER/WER numbers"
	@echo "  make docker      docker compose up --build"
	@echo "  make docker-down Stop and remove the stack"

setup:
	cd backend && python3.11 -m venv .venv && ./.venv/bin/pip install -U pip \
		&& ./.venv/bin/pip install -r requirements.txt
	cd frontend && npm install
	python3 sample_documents/generate_documents.py || true
	python3 sample_data/generate_seed.py || true

backend:
	cd backend && ./.venv/bin/uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

dev:
	@echo "Starting API on :8000 and web app on :5173 ..."
	@(cd backend && ./.venv/bin/uvicorn app.main:app --port 8000 &) ; \
	 cd frontend && npm run dev

seed:
	cd backend && ./.venv/bin/python -c "from app.db.init_db import init_database; print(init_database())"

reset:
	./backend/.venv/bin/python backend/scripts/reset_demo.py --yes

test:
	./backend/.venv/bin/python backend/tests/test_hero_flow.py

# ---- Handwriting recognition (optional, ~1.3 GB of weights) ----
htr-setup:
	./backend/.venv/bin/pip install -r backend/requirements-ai.txt
	./backend/.venv/bin/python scripts/download_models.py trocr-base-handwritten-en

htr-test:
	./backend/.venv/bin/python tests/test_htr_smoke.py

htr-eval:
	./backend/.venv/bin/python scripts/evaluate_htr.py --show-errors

htr-models:
	./backend/.venv/bin/python htr_infer.py --list-models

docker:
	docker compose up --build

docker-down:
	docker compose down -v

clean:
	rm -rf backend/.venv frontend/node_modules frontend/dist storage
