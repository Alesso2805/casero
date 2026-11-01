from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid7

import asyncpg
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from api_client import FixedClock
from casero.admin.application.alerts import UnansweredComplaint
from casero.admin.application.retention import ForgetExpiredData
from casero.admin.infrastructure.alerts import SqlOpsReadings
from casero.admin.infrastructure.retention import SqlRetention
from casero.shared.infrastructure.database import create_engine
from database import Database

pytestmark = pytest.mark.anyio

NOW = datetime(2029, 3, 10, 15, 0, tzinfo=UTC)


@pytest.fixture
async def owner(database: Database) -> AsyncIterator[asyncpg.Connection]:
    connection = await asyncpg.connect(database.dsn("casero_owner"))
    try:
        yield connection
    finally:
        await connection.close()


@pytest.fixture
async def engine(database: Database) -> AsyncIterator[AsyncEngine]:
    worker = create_engine(
        database.dsn("casero_worker").replace("postgresql://", "postgresql+asyncpg://", 1)
    )
    try:
        yield worker
    finally:
        await worker.dispose()


async def waitlisted(owner: asyncpg.Connection, created_at: datetime) -> UUID:
    entry_id = uuid7()
    await owner.execute(
        "INSERT INTO waitlist_entries (id, email, source, consented_at, created_at)"
        " VALUES ($1, $2, 'landing', $3, $3)",
        entry_id,
        f"{entry_id}@example.com",
        created_at,
    )
    return entry_id


async def complained(
    owner: asyncpg.Connection, created_at: datetime, number: str, due_at: date | None = None
) -> UUID:
    complaint_id = uuid7()
    await owner.execute(
        "INSERT INTO complaints (id, number, created_at, full_name, document_type,"
        " document_number, email, item_kind, kind, detail, response_channel, due_at)"
        " VALUES ($1, $2, $3, 'Rosa', 'dni', '45678912', 'rosa@example.com', 'service', 'claim',"
        " 'No funciona', 'email', $4)",
        complaint_id,
        number,
        created_at,
        due_at or created_at.date(),
    )
    return complaint_id


async def exists(owner: asyncpg.Connection, table: str, row_id: UUID) -> bool:
    found: bool = await owner.fetchval(
        f"SELECT EXISTS (SELECT 1 FROM {table} WHERE id = $1)",
        row_id,
    )
    return found


async def test_the_waitlist_goes_at_12_months_and_complaints_at_2_years(
    owner: asyncpg.Connection, engine: AsyncEngine
) -> None:
    old_entry = await waitlisted(owner, NOW - timedelta(days=366))
    new_entry = await waitlisted(owner, NOW - timedelta(days=364))
    old_complaint = await complained(owner, NOW - timedelta(days=732), "900000001-2027")
    new_complaint = await complained(owner, NOW - timedelta(days=729), "900000002-2027")

    await ForgetExpiredData(SqlRetention(engine), FixedClock(NOW))()

    assert not await exists(owner, "waitlist_entries", old_entry)
    assert await exists(owner, "waitlist_entries", new_entry)
    assert not await exists(owner, "complaints", old_complaint)
    assert await exists(owner, "complaints", new_complaint)
    await owner.execute("DELETE FROM complaints WHERE id = $1", new_complaint)


async def test_the_worker_reads_unanswered_complaints_with_the_filing_day_in_lima(
    owner: asyncpg.Connection, engine: AsyncEngine
) -> None:
    late_evening_in_lima = datetime(2029, 3, 2, 2, 0, tzinfo=UTC)
    unanswered = await complained(owner, late_evening_in_lima, "900000003-2029", date(2029, 3, 22))
    answered = await complained(owner, late_evening_in_lima, "900000004-2029")
    await owner.execute(
        "UPDATE complaints SET response = 'Listo', responded_at = $2 WHERE id = $1", answered, NOW
    )

    complaints = await SqlOpsReadings(engine).unanswered_complaints()
    await owner.execute("DELETE FROM complaints WHERE id = ANY($1)", [unanswered, answered])

    assert UnansweredComplaint("900000003-2029", date(2029, 3, 1), date(2029, 3, 22)) in complaints
    assert "900000004-2029" not in [complaint.number for complaint in complaints]
