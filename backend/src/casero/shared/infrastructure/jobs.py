from collections.abc import Awaitable, Callable
from datetime import date, datetime
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from casero.shared.infrastructure.database import set_account_context
from casero.shared.kernel.clock import Clock

# A data job that keeps failing for an account stops retrying until the next Lima day.
MAX_DAILY_ATTEMPTS = 3

CLAIM_ONCE = text(
    "INSERT INTO job_runs (job, run_key, account_id, status, attempts, started_at)"
    " VALUES (:job, :run_key, :account_id, 'running', 1, :now)"
    " ON CONFLICT DO NOTHING RETURNING job"
)
START_ATTEMPT = text(
    "INSERT INTO job_runs (job, run_key, account_id, status, attempts, started_at)"
    " VALUES (:job, :run_key, :account_id, 'running', 1, :now)"
    " ON CONFLICT (job, run_key, account_id) DO UPDATE"
    " SET status = 'running', attempts = job_runs.attempts + 1,"
    " started_at = EXCLUDED.started_at, finished_at = NULL, error_code = NULL"
    " WHERE job_runs.status <> 'done' AND job_runs.attempts < :max_attempts"
    " RETURNING job"
)
FINISH = text(
    "UPDATE job_runs SET status = :status, finished_at = :now, error_code = :error_code"
    " WHERE job = :job AND run_key = :run_key AND account_id IS NOT DISTINCT FROM :account_id"
)
DONE = text(
    "SELECT EXISTS (SELECT 1 FROM job_runs WHERE job = :job AND run_key = :run_key"
    " AND account_id IS NOT DISTINCT FROM :account_id AND status = 'done')"
)
ACCOUNTS = text("SELECT app_list_account_ids(:purpose, :today)")

type AccountWork = Callable[[AsyncConnection, UUID, date], Awaitable[None]]

log = structlog.get_logger()


def run_parameters(job: str, run_key: str, account_id: UUID | None) -> dict[str, object]:
    return {"job": job, "run_key": run_key, "account_id": account_id}


async def claim_once(
    connection: AsyncConnection, job: str, run_key: str, account_id: UUID | None, now: datetime
) -> bool:
    """Records the run before its effect, so an email goes out at most once (rule 12)."""
    claimed = await connection.execute(
        CLAIM_ONCE, {**run_parameters(job, run_key, account_id), "now": now}
    )
    return claimed.first() is not None


async def start_attempt(
    connection: AsyncConnection, job: str, run_key: str, account_id: UUID | None, now: datetime
) -> bool:
    started = await connection.execute(
        START_ATTEMPT,
        {
            **run_parameters(job, run_key, account_id),
            "now": now,
            "max_attempts": MAX_DAILY_ATTEMPTS,
        },
    )
    return started.first() is not None


async def finish_run(
    connection: AsyncConnection,
    job: str,
    run_key: str,
    account_id: UUID | None,
    now: datetime,
    error_code: str | None = None,
) -> None:
    await connection.execute(
        FINISH,
        {
            **run_parameters(job, run_key, account_id),
            "now": now,
            "status": "failed" if error_code else "done",
            "error_code": error_code,
        },
    )


async def is_done(
    connection: AsyncConnection, job: str, run_key: str, account_id: UUID | None
) -> bool:
    done: bool = (
        await connection.execute(DONE, run_parameters(job, run_key, account_id))
    ).scalar_one()
    return done


class DailyAccountJob:
    """Brings every account's data up to the current Lima day, once per day (rule 12).

    Each account runs in its own transaction with its RLS context and marks itself done in
    that same transaction, so a crash leaves the account to be retried on the next tick.
    """

    def __init__(self, engine: AsyncEngine, clock: Clock, name: str, work: AccountWork) -> None:
        self._engine = engine
        self._clock = clock
        self._name = name
        self._work = work

    async def __call__(self) -> None:
        today = self._clock.today_lima()
        run_key = today.isoformat()
        async with self._engine.begin() as connection:
            if await is_done(connection, self._name, run_key, None):
                return
            accounts = [
                row[0]
                for row in await connection.execute(ACCOUNTS, {"purpose": "jobs", "today": today})
            ]
        finished = [await self._run(account_id, today, run_key) for account_id in accounts]
        if all(finished):
            async with self._engine.begin() as connection:
                if await claim_once(connection, self._name, run_key, None, self._clock.now()):
                    await finish_run(connection, self._name, run_key, None, self._clock.now())

    async def _run(self, account_id: UUID, today: date, run_key: str) -> bool:
        async with self._engine.begin() as connection:
            if await is_done(connection, self._name, run_key, account_id):
                return True
            if not await start_attempt(
                connection, self._name, run_key, account_id, self._clock.now()
            ):
                return False
        try:
            async with self._engine.begin() as connection:
                await set_account_context(connection, account_id)
                await self._work(connection, account_id, today)
                await finish_run(connection, self._name, run_key, account_id, self._clock.now())
        except Exception as error:
            # Only the type: exception messages can carry personal data (rule 8).
            log.error("worker.account_job_failed", job=self._name, error=type(error).__name__)
            async with self._engine.begin() as connection:
                await finish_run(
                    connection,
                    self._name,
                    run_key,
                    account_id,
                    self._clock.now(),
                    type(error).__name__,
                )
            return False
        return True
