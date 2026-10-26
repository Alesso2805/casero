.PHONY: up down test lint migrate check-bucket-policy

up:
	docker compose up --detach --build

down:
	docker compose down

test:
	cd backend && uv run pytest
	cd web && pnpm run test

lint:
	cd backend && uv run ruff check && uv run ruff format --check && uv run mypy && uv run lint-imports
	cd web && pnpm run lint && pnpm run typecheck

migrate:
	docker compose run --rm migrate

check-bucket-policy:
	cd backend && uv run python scripts/check_bucket_policy.py
