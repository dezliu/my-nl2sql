.PHONY: up down migrate seed api worker web admin test

up:
	docker compose up -d

down:
	docker compose down

migrate:
	alembic upgrade head

seed:
	python -m backend.scripts.seed

api:
	uvicorn backend.api.main:app --reload --port 8000

worker:
	celery -A backend.workers.tasks worker --loglevel=info

web:
	npm run dev:web

admin:
	npm run dev:admin

test:
	pytest backend/tests -q

install:
	pip install -e ".[dev]"
	npm install
