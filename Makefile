VENV ?= .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
CELERY := $(VENV)/bin/celery
UVICORN := $(VENV)/bin/uvicorn
ALEMBIC := $(VENV)/bin/alembic
PYTEST := $(VENV)/bin/pytest

.PHONY: up down migrate seed upgrade-prompts api worker web admin test install eval-rag

up:
	docker compose up -d

down:
	docker compose down

migrate:
	$(ALEMBIC) upgrade head

seed:
	$(PY) -m backend.scripts.seed

upgrade-prompts:
	$(PY) -m backend.scripts.upgrade_prompts

api:
	$(UVICORN) backend.api.main:app --reload --port 8000

worker:
	$(CELERY) -A backend.workers.tasks worker --loglevel=info

web:
	npm run dev:web

admin:
	npm run dev:admin

test:
	$(PYTEST) backend/tests -q

eval-rag:
	$(PY) -m backend.scripts.eval_rag --import-benchmark

install:
	$(PIP) install -e ".[dev]"
	npm install
