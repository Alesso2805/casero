from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid7

import asyncpg
import pytest

from api_client import FixedClock
from database import Database
from tax_flows import add_renter, client_for, pay, register, save_ruc, send, start_leases

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 27, 15, 0, tzinfo=UTC)
UPCOMING = "/api/app/tax/upcoming"


async def verify(database: Database, email: str) -> None:
    owner = await asyncpg.connect(database.dsn("casero_owner"))
    try:
        await owner.execute("UPDATE users SET email_verified_at = $1 WHERE email = $2", NOW, email)
    finally:
        await owner.close()


async def test_the_notice_shows_in_the_last_five_days_until_paid(
    database: Database, request: pytest.FixtureRequest
) -> None:
    clock = FixedClock(NOW)
    email = f"{uuid7()}@example.com"
    with client_for(database, request, clock) as client:
        register(client, email)
        await verify(database, email)
        save_ruc(client)
        ana = add_renter(client, "Ana", {"doc_type": "dni", "number": "45678912"})
        [lease] = start_leases(client, {"renter_id": ana})
        pay(client, lease, 56_000, "2026-10-05")
        seen: list[Any] = []
        for day in (13, 14, 19, 20):
            clock.advance(datetime(2026, 11, day, 15, tzinfo=UTC) - clock.now())
            seen.append(client.get(UPCOMING).json())
        clock.advance(timedelta(days=-2))
        body = {
            "id": str(uuid7()),
            "period": "2026-10",
            "renter_id": ana,
            "amount_cents": 2_800,
            "paid_on": "2026-11-18",
            "order_number": "1234567890",
            "declared_base_cents": 56_000,
        }
        assert send(client, "POST", "/api/app/tax/payments", body).status_code == 201
        paid = client.get(UPCOMING).json()

    notice = {
        "period": "2026-10",
        "due_on": "2026-11-19",
        "pending_cents": 2_800,
        "declarations": 1,
    }
    assert seen == [None, {**notice, "days_left": 5}, {**notice, "days_left": 0}, None]
    assert paid is None


async def test_without_a_ruc_there_is_no_due_date_to_warn_about(
    database: Database, request: pytest.FixtureRequest
) -> None:
    clock = FixedClock(NOW)
    email = f"{uuid7()}@example.com"
    with client_for(database, request, clock) as client:
        register(client, email)
        await verify(database, email)
        ana = add_renter(client, "Ana", {"doc_type": "dni", "number": "45678912"})
        [lease] = start_leases(client, {"renter_id": ana})
        pay(client, lease, 56_000, "2026-10-05")
        clock.advance(datetime(2026, 11, 15, 15, tzinfo=UTC) - clock.now())
        response = client.get(UPCOMING)

    assert (response.status_code, response.json()) == (200, None)
