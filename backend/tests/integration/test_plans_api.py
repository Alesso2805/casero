from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid7

import asyncpg
import pytest

from api_client import FixedClock
from database import Database
from tax_flows import add_renter, client_for, pay, register, save_ruc, start_leases

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 27, 15, 0, tzinfo=UTC)
ENDS_ON_WEEK_LATER = "2026-11-02"


async def owner_run(database: Database, query: str, *args: object) -> None:
    owner = await asyncpg.connect(database.dsn("casero_owner"))
    try:
        await owner.execute(query, *args)
    finally:
        await owner.close()


async def test_the_plans_come_from_the_cheapest_with_their_prices(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with client_for(database, request, FixedClock(NOW)) as client:
        anonymous = client.get("/api/app/plans")
        register(client)
        plans = client.get("/api/app/plans")

    assert anonymous.status_code == 401
    assert [(plan["code"], plan["max_active_leases"]) for plan in plans.json()] == [
        ("free", 1),
        ("casero", 10),
    ]
    free, casero = plans.json()
    assert (free["price_month_cents"], free["price_year_cents"]) == (0, 0)
    assert casero["price_month_cents"] > 0
    assert casero["price_year_cents"] > casero["price_month_cents"]


async def test_a_lapsed_trial_shows_its_last_day_and_what_is_owed_to_sunat(
    database: Database, request: pytest.FixtureRequest
) -> None:
    clock = FixedClock(NOW)
    email = f"{uuid7()}@example.com"
    with client_for(database, request, clock) as client:
        register(client, email)
        save_ruc(client)
        ana = add_renter(client, "Ana", {"doc_type": "dni", "number": "45678912"})
        [lease] = start_leases(client, {"renter_id": ana})
        pay(client, lease, 80_000, "2026-10-05")
        during_the_trial = client.get("/api/app/account").json()
        await owner_run(
            database, "UPDATE users SET email_verified_at = $1 WHERE email = $2", NOW, email
        )
        await owner_run(
            database,
            "UPDATE subscriptions s SET trial_ends_at = $2::date, ends_at = $2::date"
            " FROM renters r WHERE r.account_id = s.account_id AND r.id = $1",
            UUID(ana),
            datetime(2026, 11, 2, tzinfo=UTC).date(),
        )
        clock.advance(timedelta(days=8))
        lapsing = client.get("/api/app/account").json()
        dues = client.get("/api/app/tax/pending-dues").json()
        clock.advance(timedelta(days=5))
        client.get("/api/app/account")
        clock.advance(timedelta(days=3))
        gone = client.get("/api/app/account").json()
        none = client.get("/api/app/tax/pending-dues").json()

    assert during_the_trial["grace_until"] is None
    assert (lapsing["status"], lapsing["grace_until"]) == ("grace", "2026-11-08")
    assert dues == [{"period": "2026-10", "due_on": "2026-11-19", "pending_cents": 4_000}]
    assert (gone["status"], gone["grace_until"]) == ("free", None)
    assert none == []
