FROM ghcr.io/astral-sh/uv:0.11.25 AS uv

# Built from the repository root so the image carries infra/seed/tax (CLAUDE.md, rule 6).
FROM python:3.14-slim-trixie
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    CASERO_TAX_SEED_DIR=/app/seed/tax
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock backend/.python-version ./
RUN uv sync --locked --no-dev --no-install-project
COPY backend/alembic.ini ./
COPY backend/migrations ./migrations
COPY backend/src ./src
COPY infra/seed/tax ./seed/tax
RUN uv sync --locked --no-dev
RUN useradd --system --uid 10001 --no-create-home casero
USER casero
