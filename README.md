# Casero

A web app (PWA) for small Peruvian landlords. It shows who owes rent, prepares the collection message for WhatsApp, and gets each tenant's monthly SUNAT Form 1683 ready with its amount and due date.

The specification is in [docs/SPEC.md](docs/SPEC.md) (in Spanish), the backlog in [docs/BACKLOG.md](docs/BACKLOG.md), and the architecture decisions in [docs/adr/](docs/adr/). The architecture rules and their tests are listed in [docs/ARCHITECTURE_RULES.md](docs/ARCHITECTURE_RULES.md).

## Development

Requirements: [uv](https://docs.astral.sh/uv/), Node 26 and pnpm 12.

Backend checks, run from `backend/`:

```sh
uv sync
uv run ruff check && uv run ruff format --check
uv run mypy
uv run lint-imports
uv run pytest
```

Frontend checks, run from `web/`:

```sh
pnpm install
pnpm run lint && pnpm run typecheck && pnpm run test && pnpm run build
```

After changing an endpoint, regenerate the API types:

```sh
cd backend && uv run python scripts/export_openapi.py ../web/src/api/openapi.json
cd ../web && pnpm run generate:api
```

## License

Copyright © 2026 Alessandro David. All rights reserved.

This repository is public so that its code and design can be read. Beyond what GitHub's Terms of Service allow (viewing and forking on GitHub), no license is granted. You may not use, copy, modify or distribute any part of it without written permission.
