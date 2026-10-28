from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid7

import asyncpg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine

from api_client import FixedClock, address_for, api_client
from casero.shared.infrastructure.database import create_engine, set_account_context
from casero.worker import account_jobs
from database import Database

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 27, 15, 0, tzinfo=UTC)
CSRF = "__Host-casero_csrf"


def send(client: TestClient, method: str, path: str, body: object = None) -> Any:
    return client.request(method, path, json=body, headers={"X-CSRF-Token": client.cookies[CSRF]})


def new_lease(database: Database, name: str, **overrides: object) -> str:
    """Registers an account with one unit and one renter, and starts a lease on it."""
    with api_client(
        database, address_for(name), FixedClock(NOW), registration_mode="open"
    ) as client:
        client.get("/api/public/csrf")
        assert (
            send(
                client,
                "POST",
                "/api/public/registration",
                {
                    "email": f"{uuid7()}@example.com",
                    "password": "una clave bien larga",
                    "display_name": "Casera",
                    "accept_terms_and_privacy": True,
                    "consent_sensitive_data": True,
                },
            ).status_code
            == 201
        )
        house = send(
            client,
            "POST",
            "/api/app/properties",
            {"name": "Casa", "ownership": "sole", "units": [{"name": "Cuarto", "kind": "room"}]},
        ).json()
        renter = send(client, "POST", "/api/app/renters", {"full_name": "Ana"}).json()
        body = {
            "id": str(uuid7()),
            "unit_id": house["units"][0]["id"],
            "renter_id": renter["id"],
            "monthly_rent_cents": 80_000,
            "due_day": 31,
            "start_date": "2025-06-01",
            "control_from_period": "2026-09",
            "tax_treatment": "standard",
            **overrides,
        }
        response = send(client, "POST", "/api/app/leases", body)
        assert response.status_code == 201, response.text
        return str(body["id"])


async def owner(database: Database, query: str, *args: object) -> list[asyncpg.Record]:
    connection = await asyncpg.connect(database.dsn("casero_owner"))
    try:
        return await connection.fetch(query, *args)
    finally:
        await connection.close()


async def rents(database: Database, lease_id: str) -> list[tuple[str, int, str]]:
    rows = await owner(
        database,
        "SELECT period, amount_cents, due_date::text FROM charges"
        " WHERE lease_id = $1::uuid AND kind = 'rent' ORDER BY period",
        lease_id,
    )
    return [(row[0], row[1], row[2]) for row in rows]


@pytest.fixture
async def worker_engine(database: Database) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(
        database.dsn("casero_worker").replace("postgresql://", "postgresql+asyncpg://", 1)
    )
    yield engine
    await engine.dispose()


async def run_day(database: Database, engine: AsyncEngine, lease_id: str, today: date) -> None:
    """Runs the account's daily data jobs as the worker does, for that lease's account."""
    [row] = await owner(database, "SELECT account_id FROM leases WHERE id = $1::uuid", lease_id)
    account_id: UUID = row["account_id"]
    clock = FixedClock(datetime(today.year, today.month, today.day, 12, tzinfo=UTC))
    for work in account_jobs(clock).values():
        async with engine.begin() as connection:
            await set_account_context(connection, account_id)
            await work(connection, account_id, today)


async def test_a_new_lease_is_charged_up_to_today_at_once(
    database: Database, request: pytest.FixtureRequest
) -> None:
    lease_id = new_lease(database, request.node.name)

    assert await rents(database, lease_id) == [
        ("2026-09", 80_000, "2026-09-30"),
        ("2026-10", 80_000, "2026-10-31"),
    ]


async def test_the_worker_catches_up_after_two_days_down_and_runs_once(
    database: Database, request: pytest.FixtureRequest, worker_engine: AsyncEngine
) -> None:
    lease_id = new_lease(database, request.node.name)

    await run_day(database, worker_engine, lease_id, date(2026, 11, 2))
    await run_day(database, worker_engine, lease_id, date(2026, 11, 2))
    await run_day(database, worker_engine, lease_id, date(2027, 2, 1))

    assert await rents(database, lease_id) == [
        ("2026-09", 80_000, "2026-09-30"),
        ("2026-10", 80_000, "2026-10-31"),
        ("2026-11", 80_000, "2026-11-30"),
        ("2026-12", 80_000, "2026-12-31"),
        ("2027-01", 80_000, "2027-01-31"),
        ("2027-02", 80_000, "2027-02-28"),
    ]


async def test_a_rent_change_applies_from_its_period(
    database: Database, request: pytest.FixtureRequest, worker_engine: AsyncEngine
) -> None:
    lease_id = new_lease(database, request.node.name)
    await owner(
        database,
        "INSERT INTO lease_rent_changes (id, account_id, lease_id, monthly_rent_cents,"
        " effective_period, created_by, created_at) SELECT $1::uuid, l.account_id, l.id, 95000,"
        " '2026-12', m.user_id, $2 FROM leases l"
        " JOIN account_members m ON m.account_id = l.account_id WHERE l.id = $3::uuid",
        uuid7(),
        NOW,
        lease_id,
    )

    await run_day(database, worker_engine, lease_id, date(2026, 12, 1))

    assert [amount for _, amount, _ in await rents(database, lease_id)] == [
        80_000,
        80_000,
        80_000,
        95_000,
    ]


async def test_a_voided_rent_is_not_charged_again(
    database: Database, request: pytest.FixtureRequest, worker_engine: AsyncEngine
) -> None:
    lease_id = new_lease(database, request.node.name)
    await owner(
        database,
        "INSERT INTO charge_voids (charge_id, account_id, reason, voided_by, voided_at)"
        " SELECT c.id, c.account_id, 'Mes no alquilado', m.user_id, $2 FROM charges c"
        " JOIN account_members m ON m.account_id = c.account_id"
        " WHERE c.lease_id = $1::uuid AND c.period = '2026-10'",
        lease_id,
        NOW,
    )

    await run_day(database, worker_engine, lease_id, date(2026, 10, 28))

    assert [period for period, _, _ in await rents(database, lease_id)] == ["2026-09", "2026-10"]


async def test_a_lease_past_its_planned_end_closes_and_stops_charging(
    database: Database, request: pytest.FixtureRequest, worker_engine: AsyncEngine
) -> None:
    lease_id = new_lease(database, request.node.name, end_date="2026-11-15")

    await run_day(database, worker_engine, lease_id, date(2026, 11, 20))
    await run_day(database, worker_engine, lease_id, date(2027, 1, 5))

    [lease] = await owner(database, "SELECT ended_at FROM leases WHERE id = $1::uuid", lease_id)
    assert lease["ended_at"] == date(2026, 11, 15)
    assert [period for period, _, _ in await rents(database, lease_id)] == [
        "2026-09",
        "2026-10",
        "2026-11",
    ]
    audit = await owner(
        database,
        "SELECT action, actor_user_id, changed_fields FROM audit_log WHERE entity_id = $1::uuid"
        " AND action = 'lease.closed'",
        lease_id,
    )
    assert [(row["actor_user_id"], list(row["changed_fields"])) for row in audit] == [
        (None, ["ended_at"])
    ]
