from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid7

import asyncpg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine

from api_client import FixedClock
from casero.accounts.application.entitlements import GetEntitlements
from casero.accounts.infrastructure.account import SqlPlans, SqlSubscriptions
from casero.leases.application.tools import EnsureLeaseTools
from casero.leases.infrastructure.tools import SqlLeaseTools
from casero.shared.infrastructure.audit import SqlAuditLog
from casero.shared.infrastructure.database import create_engine, set_account_context
from database import Database
from tax_flows import add_renter, client_for, register, send, start_leases

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 27, 15, 0, tzinfo=UTC)
TOOLS = "/api/app/lease-tools"


async def account_of(database: Database, renter_id: str) -> UUID:
    owner = await asyncpg.connect(database.dsn("casero_owner"))
    try:
        account_id: UUID = await owner.fetchval(
            "SELECT account_id FROM renters WHERE id = $1", UUID(renter_id)
        )
        return account_id
    finally:
        await owner.close()


async def set_ages(database: Database, lease_ids: list[str], created_at: list[datetime]) -> None:
    owner = await asyncpg.connect(database.dsn("casero_owner"))
    try:
        for lease_id, at in zip(lease_ids, created_at, strict=True):
            await owner.execute(
                "UPDATE leases SET created_at = $2 WHERE id = $1", UUID(lease_id), at
            )
    finally:
        await owner.close()


async def landlord_with_leases(
    database: Database, client: TestClient, count: int
) -> tuple[str, list[str]]:
    email = f"{uuid7()}@example.com"
    register(client, email)
    owner = await asyncpg.connect(database.dsn("casero_owner"))
    try:
        await owner.execute("UPDATE users SET email_verified_at = $1 WHERE email = $2", NOW, email)
    finally:
        await owner.close()
    renters = [add_renter(client, f"Inquilino {n}") for n in range(count)]
    terms: list[dict[str, object]] = [{"renter_id": renter} for renter in renters]
    return renters[0], start_leases(client, *terms)


def past_the_trial_and_its_grace(client: TestClient, clock: FixedClock) -> None:
    clock.advance(timedelta(days=29))
    assert client.get("/api/app/account").status_code == 200
    clock.advance(timedelta(days=9))


async def ensure_tools(database: Database, account_id: UUID, clock: FixedClock) -> None:
    engine: AsyncEngine = create_engine(
        database.dsn("casero_worker").replace("postgresql://", "postgresql+asyncpg://", 1)
    )
    try:
        async with engine.begin() as connection:
            await set_account_context(connection, account_id)
            entitlements = GetEntitlements(
                SqlSubscriptions(connection), SqlPlans(connection), clock
            )
            await EnsureLeaseTools(
                entitlements, SqlLeaseTools(connection), SqlAuditLog(connection), clock
            )(account_id)
    finally:
        await engine.dispose()


def flags(status: Any) -> dict[str, bool]:
    return {lease["lease_id"]: lease["tools_enabled"] for lease in status["leases"]}


async def test_after_the_trial_only_the_oldest_keeps_the_tools_until_the_landlord_chooses(
    database: Database, request: pytest.FixtureRequest
) -> None:
    clock = FixedClock(NOW)
    with client_for(database, request, clock) as client:
        renter, (oldest, newest, other) = await landlord_with_leases(database, client, 3)
        await set_ages(
            database,
            [oldest, newest, other],
            [NOW, NOW + timedelta(minutes=1), NOW + timedelta(minutes=2)],
        )
        account_id = await account_of(database, renter)
        during_the_trial = client.get(TOOLS).json()
        past_the_trial_and_its_grace(client, clock)
        await ensure_tools(database, account_id, clock)
        lapsed = client.get(TOOLS).json()
        chosen = send(client, "PUT", TOOLS, {"lease_ids": [newest]})
        too_many = send(client, "PUT", TOOLS, {"lease_ids": [oldest, newest]})
        foreign = send(client, "PUT", TOOLS, {"lease_ids": [str(uuid7())]})
        await ensure_tools(database, account_id, clock)
        settled = client.get(TOOLS).json()

    assert during_the_trial["limit"] == 10
    assert during_the_trial["over_limit"] is False
    assert set(flags(during_the_trial).values()) == {True}
    assert (lapsed["limit"], lapsed["over_limit"]) == (1, True)
    assert flags(lapsed) == {oldest: True, newest: False, other: False}
    assert flags(chosen.json()) == {oldest: False, newest: True, other: False}
    assert (too_many.status_code, too_many.json()["detail"]) == (422, "too_many_leases")
    assert (foreign.status_code, foreign.json()["detail"]) == (404, "lease_not_found")
    assert flags(settled) == {oldest: False, newest: True, other: False}


async def test_a_paid_plan_gives_the_tools_back(
    database: Database, request: pytest.FixtureRequest
) -> None:
    clock = FixedClock(NOW)
    with client_for(database, request, clock) as client:
        renter, leases = await landlord_with_leases(database, client, 2)
        account_id = await account_of(database, renter)
        past_the_trial_and_its_grace(client, clock)
        await ensure_tools(database, account_id, clock)
        lapsed = client.get(TOOLS).json()
        owner = await asyncpg.connect(database.dsn("casero_owner"))
        try:
            await owner.execute(
                "UPDATE subscriptions SET ends_at = $2 WHERE account_id = $1",
                account_id,
                date(2027, 12, 31),
            )
        finally:
            await owner.close()
        await ensure_tools(database, account_id, clock)
        paid = client.get(TOOLS).json()

    assert sorted(flags(lapsed).values()) == [False, True]
    assert flags(paid) == dict.fromkeys(leases, True)


async def test_a_lease_without_the_tools_loses_the_portal_but_keeps_its_rents(
    database: Database, request: pytest.FixtureRequest
) -> None:
    clock = FixedClock(NOW)
    with client_for(database, request, clock) as client:
        renter, (first, second) = await landlord_with_leases(database, client, 2)
        await set_ages(database, [first, second], [NOW, NOW + timedelta(minutes=1)])
        account_id = await account_of(database, renter)
        past_the_trial_and_its_grace(client, clock)
        await ensure_tools(database, account_id, clock)
        kept = send(client, "POST", f"/api/app/leases/{first}/tenant-link")
        cut = send(client, "POST", f"/api/app/leases/{second}/tenant-link")
        statement = client.get(f"/api/app/leases/{second}/statement")

    assert kept.status_code == 201
    assert (cut.status_code, cut.json()["detail"]) == (403, "portal_unavailable")
    assert statement.status_code == 200


async def test_each_account_chooses_only_its_own_leases(
    database: Database, request: pytest.FixtureRequest
) -> None:
    clock = FixedClock(NOW)
    with client_for(database, request, clock) as ana, client_for(database, request, clock) as luis:
        _, leases = await landlord_with_leases(database, ana, 1)
        register(luis)
        response = send(luis, "PUT", TOOLS, {"lease_ids": leases})

    assert response.status_code == 404
