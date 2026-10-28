from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import uuid7

import asyncpg
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from casero.admin.infrastructure.alerts import SqlAlertLog, SqlOpsReadings
from casero.shared.infrastructure.database import create_engine
from database import Database

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 28, 15, 0, tzinfo=UTC)


@pytest.fixture
async def worker_engine(database: Database) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(
        database.dsn("casero_worker").replace("postgresql://", "postgresql+asyncpg://", 1)
    )
    yield engine
    await engine.dispose()


async def owner(database: Database, query: str, *args: object) -> None:
    connection = await asyncpg.connect(database.dsn("casero_owner"))
    try:
        await connection.execute(query, *args)
    finally:
        await connection.close()


async def test_the_worker_reads_stuck_emails_schedules_and_failures(
    database: Database, worker_engine: AsyncEngine
) -> None:
    stuck, fresh, failed_job = str(uuid7()), str(uuid7()), f"test-{uuid7()}"
    cut_off, running = f"test-cut-{uuid7()}", f"test-running-{uuid7()}"
    await owner(
        database,
        "INSERT INTO job_runs (job, run_key, status, attempts, started_at) VALUES"
        " ('complaint_copy', $1, 'running', 1, $2), ('complaint_copy', $3, 'running', 1, $4)",
        stuck,
        NOW - timedelta(minutes=15),
        fresh,
        NOW - timedelta(minutes=2),
    )
    await owner(
        database,
        "INSERT INTO job_runs (job, run_key, status, attempts, started_at, finished_at)"
        " VALUES ($1, '2026-10-28', 'failed', 3, $2, $2)",
        failed_job,
        NOW - timedelta(hours=1),
    )
    await owner(
        database,
        "INSERT INTO job_runs (job, run_key, status, attempts, started_at) VALUES"
        " ($1, '2026-10-28', 'running', 1, $2), ($3, '2026-10-28', 'running', 1, $4)",
        cut_off,
        NOW - timedelta(minutes=45),
        running,
        NOW - timedelta(minutes=5),
    )
    readings = SqlOpsReadings(worker_engine)

    stuck_runs = await readings.stuck_email_runs(NOW - timedelta(minutes=10))
    failures = await readings.failed_runs_since(NOW - timedelta(days=1))
    stuck_jobs = await readings.stuck_job_runs(NOW - timedelta(minutes=30))

    assert ("complaint_copy", stuck) in stuck_runs
    assert ("complaint_copy", fresh) not in stuck_runs
    assert failures[failed_job] == 1
    assert cut_off in stuck_jobs
    assert running not in stuck_jobs
    assert "complaint_copy" not in stuck_jobs
    assert await readings.schedule_rows(2026) == 84
    assert await readings.schedule_rows(2031) == 0


async def test_each_alert_is_claimed_once(worker_engine: AsyncEngine) -> None:
    alerts = SqlAlertLog(worker_engine)
    key = f"test:{uuid7()}"

    assert await alerts.claim(key, NOW)
    assert not await alerts.claim(key, NOW)
