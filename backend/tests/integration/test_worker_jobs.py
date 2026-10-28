import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid7

import asyncpg
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from api_client import FixedClock, address_for, api_client
from casero.shared.infrastructure.database import create_engine
from casero.shared.infrastructure.jobs import MAX_DAILY_ATTEMPTS, DailyAccountJob
from casero.worker import serve
from database import Database

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 27, 15, 0, tzinfo=UTC)
CSRF = "__Host-casero_csrf"
VISIBLE_ACCOUNTS = text("SELECT id FROM accounts")


def register(database: Database, name: str) -> str:
    email = f"{uuid7()}@example.com"
    with api_client(
        database, address_for(name), FixedClock(NOW), registration_mode="open"
    ) as client:
        client.get("/api/public/csrf")
        response = client.post(
            "/api/public/registration",
            json={
                "email": email,
                "password": "una clave bien larga",
                "display_name": name,
                "accept_terms_and_privacy": True,
                "consent_sensitive_data": True,
            },
            headers={"X-CSRF-Token": client.cookies[CSRF]},
        )
        assert response.status_code == 201
    return email


async def account_of(database: Database, email: str) -> UUID:
    owner = await asyncpg.connect(database.dsn("casero_owner"))
    try:
        account_id: UUID = await owner.fetchval(
            "SELECT m.account_id FROM account_members m JOIN users u ON u.id = m.user_id"
            " WHERE u.email = $1",
            email,
        )
        return account_id
    finally:
        await owner.close()


async def two_accounts(database: Database, request: pytest.FixtureRequest) -> list[UUID]:
    emails = [register(database, f"{request.node.name}-{index}") for index in range(2)]
    return [await account_of(database, email) for email in emails]


@pytest.fixture
async def worker_engine(database: Database) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(
        database.dsn("casero_worker").replace("postgresql://", "postgresql+asyncpg://", 1)
    )
    yield engine
    await engine.dispose()


async def runs(database: Database, job: str) -> dict[UUID | None, tuple[str, int]]:
    owner = await asyncpg.connect(database.dsn("casero_owner"))
    try:
        rows = await owner.fetch(
            "SELECT account_id, status, attempts FROM job_runs WHERE job = $1", job
        )
    finally:
        await owner.close()
    return {row["account_id"]: (row["status"], row["attempts"]) for row in rows}


async def test_each_account_runs_once_a_day_in_its_own_context(
    database: Database, request: pytest.FixtureRequest, worker_engine: AsyncEngine
) -> None:
    ours = await two_accounts(database, request)
    job = f"test-{uuid7()}"
    seen: dict[UUID, list[UUID]] = {}
    days: set[date] = set()

    async def work(connection: AsyncConnection, account_id: UUID, today: date) -> None:
        days.add(today)
        seen[account_id] = [row[0] for row in await connection.execute(VISIBLE_ACCOUNTS)]

    clock = FixedClock(NOW)
    daily = DailyAccountJob(worker_engine, clock, job, work)
    await daily()
    first_pass = dict(seen)
    seen.clear()
    await daily()

    assert all(first_pass[account] == [account] for account in ours)
    assert seen == {}
    recorded = await runs(database, job)
    assert all(recorded[account] == ("done", 1) for account in ours)
    assert recorded[None] == ("done", 1)

    clock.advance(timedelta(days=1))
    await daily()
    assert set(ours) <= set(seen)
    assert days == {date(2026, 10, 27), date(2026, 10, 28)}


async def test_a_failing_account_retries_up_to_three_times_without_stopping_others(
    database: Database, request: pytest.FixtureRequest, worker_engine: AsyncEngine
) -> None:
    broken, healthy = await two_accounts(database, request)
    job = f"test-{uuid7()}"
    calls: list[UUID] = []

    async def work(connection: AsyncConnection, account_id: UUID, today: date) -> None:
        calls.append(account_id)
        await connection.execute(text("SELECT 1"))
        if account_id == broken:
            raise RuntimeError("Key (email)=(ana@example.com) already exists.")

    daily = DailyAccountJob(worker_engine, FixedClock(NOW), job, work)
    for _ in range(MAX_DAILY_ATTEMPTS + 1):
        await daily()

    recorded = await runs(database, job)
    assert recorded[broken] == ("failed", MAX_DAILY_ATTEMPTS)
    assert recorded[healthy] == ("done", 1)
    assert None not in recorded
    assert calls.count(broken) == MAX_DAILY_ATTEMPTS
    assert calls.count(healthy) == 1


class Lock:
    def __init__(self, alive: bool = True) -> None:
        self.alive = alive

    async def fetchval(self, query: str) -> int:
        if not self.alive:
            raise asyncpg.ConnectionDoesNotExistError("connection was closed")
        return 1


async def no_heartbeat() -> None:
    return None


async def test_the_worker_stops_when_asked_and_fails_without_its_lock() -> None:
    stop = asyncio.Event()
    ticks: list[int] = []

    async def job() -> None:
        ticks.append(len(ticks))
        if len(ticks) == 2:
            stop.set()

    await serve({"job": job}, Lock(), stop, 0, no_heartbeat)  # type: ignore[arg-type]

    assert ticks == [0, 1]
    with pytest.raises(asyncpg.ConnectionDoesNotExistError):
        await serve({"job": job}, Lock(alive=False), asyncio.Event(), 0, no_heartbeat)  # type: ignore[arg-type]


async def test_the_heartbeat_follows_only_ticks_without_a_crash() -> None:
    stop = asyncio.Event()
    beats: list[int] = []
    ticks = 0

    async def job() -> None:
        nonlocal ticks
        ticks += 1
        if ticks == 2:
            raise RuntimeError
        if ticks == 3:
            stop.set()

    async def heartbeat() -> None:
        beats.append(ticks)

    await serve({"job": job}, Lock(), stop, 0, heartbeat)  # type: ignore[arg-type]

    assert beats == [1, 3]
