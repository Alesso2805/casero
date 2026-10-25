# ADR-0001: Modular monolith with separate API and worker processes

- Status: Accepted
- Date: 2026-10-25
- Story: CS-01

## Context

Casero is built and operated by one person on a single virtual server with a budget of about US$30 a month. It needs an HTTP API, scheduled jobs (charge generation, tax reminders, purges, alerts) and clear module boundaries that CI can check, so the codebase stays maintainable without code review from a second person.

## Decision

### Processes

- One Python package, `casero`, run as two processes from the same image:
  - `casero.api`: FastAPI in a single Uvicorn process, serving `/api/*`. When `ADMIN_ENABLED=true`, the same process also runs a second Uvicorn server, bound to loopback, for the admin panel (ADR-0008).
  - `casero.worker`: a loop that wakes every minute, decides in Lima time which jobs are due and runs them.
- No scheduled work runs inside the FastAPI lifespan.
- Only one worker is active at a time: it holds `pg_try_advisory_lock` on a dedicated connection outside the SQLAlchemy pool and exits if it cannot get the lock.
- Data jobs are written as "ensure the state up to today" and are idempotent, so they recover after downtime.
- Email jobs are recorded in `job_runs` before sending and are sent at most once. Tax reminders are the exception: they retry transient errors up to 3 times on the same day.

### Modules and layers

Modules in dependency order, bottom to top:

`shared.kernel` → `identity` → `accounts` → `properties` → `leases` → `ledger` → `tax` → `reminders` → `tenant_portal` → `admin`

`shared.infrastructure` (database contexts, `Mailer`, `Storage`, crypto) sits beside the bottom of the order and is used only by `infrastructure` layers, `api` layers and the composition roots.

Each business module has four layers, top to bottom: `api`, `infrastructure`, `application`, `domain`.

| Layer | May import |
| --- | --- |
| `domain` | Standard library, `shared.kernel`, its own `domain` |
| `application` | Its own `domain`, `shared.kernel`, and the `application` layer of lower modules. Declares ports as `Protocol`s |
| `infrastructure` | Its own `application` and `domain`, `shared.kernel`, `shared.infrastructure`, SQLAlchemy and other drivers. Implements the ports |
| `api` | Its own `application`, `domain` and `infrastructure`, `shared.kernel`, `shared.infrastructure` and FastAPI |

Across modules, code may import only the `application` layer of a lower module. The composition roots, `casero/api.py` and `casero/worker.py`, may import anything and wire implementations into ports.

### Use cases that cross modules

A use case that involves several modules lives in the highest of them:

- Creating a lease with opening balances lives in `ledger.application` and calls `leases.application`.
- `leases` reads plan features and limits from `accounts.application` (the `entitlements` service).
- Registration lives in `accounts.application` and uses `identity.application` to create the user and the legal acceptances.
- Archiving a unit, which must fail while the unit has an active lease, lives in `leases.application`.

### Ports for data owned by higher modules

When a lower module needs data owned by a higher one, the dependency is inverted:

1. The lower module declares a port, a `Protocol` named for what it needs (for example `TenantLinkProvider`), in its own `application` layer.
2. The higher module implements it. It may import the lower module's `application` layer to do so, because that import goes down the order.
3. The wiring lives only in the composition roots, `casero/api.py` and `casero/worker.py`. No other file imports another module's `infrastructure` or builds an implementation of another module's port.
4. Tests of the lower module use a fake of the port.

Known cases:

- `reminders` needs the current tenant link from `tenant_portal` for `{enlace}`.
- The daily digest in `reminders` counts pending vouchers from `tenant_portal`.
- The data export in `accounts` collects a section from every module.

The pattern is rule AR-03 in `docs/ARCHITECTURE_RULES.md`.

### Toolchain

- Python 3.14, which has `uuid.uuid7()` in the standard library, and PostgreSQL 17.
- Frontend:
  - Node 26 LTS, which is LTS from 2026-10-28, and pnpm 12. During CS-02 every frontend tool ran on Node 26 (Vite 8, Vitest 5, ESLint 10, typescript-eslint 8 and openapi-typescript 7), so no fallback to Node 24 was needed.
  - TypeScript 5.9, pinned because openapi-typescript does not support TypeScript 6 or 7 yet.
- Exact versions are pinned in `backend/uv.lock` and `web/pnpm-lock.yaml`. CI pins the uv version and pins each GitHub Action by commit SHA. A compatibility check on 2026-10-25 found:
  - Every backend dependency ships wheels for CPython 3.14.
  - The base image must be pinned by tag (`python:3.14-slim-trixie`), because `python:3-slim` already points to 3.15.
  - SQLAlchemy must be installed with its `asyncio` extra.

## Consequences

- One deployable unit and one database keep operations simple. A single Uvicorn process limits throughput, which is enough for thousands of accounts.
- Boundaries are checked by CI instead of by convention.
- Ports add some indirection where a lower module needs data from a higher one. The list above should stay short; if it grows, the module order needs revisiting in a new ADR.
- The worker recovers from downtime by itself. The 12:00 cutoff for the 8:00 digest still applies.

## Enforcement (CS-02)

- An import-linter `layers` contract for the module order above.
- `forbidden` contracts so that no module imports another module's `domain`, `infrastructure` or `api`, and no `domain` or `application` layer imports FastAPI, SQLAlchemy or `shared.infrastructure`.
- A `layers` contract with one container per module for the four internal layers.
- A `forbidden` contract so that only `casero/api.py` and `casero/worker.py` import another module's `infrastructure`, plus a test that every declared port has an implementation wired in a composition root (AR-03).
- An architecture test that nothing in the FastAPI lifespan schedules work.
- An architecture test that `datetime.now()` and `date.today()` appear only inside the `Clock` implementation.
- One meta-test per AR rule, with a sample that violates the rule and must be detected.
