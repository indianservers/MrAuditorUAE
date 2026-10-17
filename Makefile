.PHONY: up down logs migrate test lint typecheck
up:
	docker compose up -d --build
down:
	docker compose down
logs:
	docker compose logs -f backend
migrate:
	docker compose exec backend alembic upgrade head
test:
	docker compose exec backend pytest --cov=app --cov-report=term-missing
lint:
	cd backend && uv run ruff check . && uv run ruff format --check .
typecheck:
	cd backend && uv run mypy app
