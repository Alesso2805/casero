.PHONY: up down test lint migrate load-tax-config invite grant-founder complaint-respond complaint-register check-bucket-policy

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

load-tax-config:
	docker compose run --rm --build migrate python -m casero.tax.infrastructure.tax_config

invite:
	docker compose run --rm migrate python -m casero.accounts.infrastructure.invites $(EMAIL)

grant-founder:
	docker compose run --rm migrate python -m casero.accounts.infrastructure.founders $(EMAIL)

complaint-respond:
	docker compose run --rm -T migrate python -m casero.worker complaint-respond $(NUMBER) $(SENT_ON) < $(FILE)

complaint-register:
	docker compose run --rm -T migrate python -m casero.worker complaint-register $(FILED_AT) < $(FILE)

check-bucket-policy:
	cd backend && uv run python scripts/check_bucket_policy.py
