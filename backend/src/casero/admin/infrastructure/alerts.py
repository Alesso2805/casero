from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from casero.admin.application.complaint_emails import COPY_JOB, NOTICE_JOB
from casero.shared.infrastructure.jobs import claim_once, finish_run

ALERT_JOB = "alert"

STUCK = text(
    "SELECT job, run_key FROM job_runs WHERE job IN (:copy_job, :notice_job)"
    " AND status = 'running' AND started_at < :before ORDER BY started_at"
)
STUCK_JOBS = text(
    "SELECT DISTINCT job FROM job_runs WHERE job NOT IN (:copy_job, :notice_job, :alert_job)"
    " AND status = 'running' AND started_at < :before ORDER BY job"
)
SCHEDULE_ROWS = text("SELECT count(*) FROM sunat_due_dates WHERE year = :year")
FAILED = text(
    "SELECT job, count(*) AS failures FROM job_runs WHERE status = 'failed'"
    " AND finished_at >= :since AND job <> :alert_job GROUP BY job"
)


class SqlOpsReadings:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def stuck_email_runs(self, started_before: datetime) -> list[tuple[str, str]]:
        async with self._engine.connect() as connection:
            rows = await connection.execute(
                STUCK,
                {"copy_job": COPY_JOB, "notice_job": NOTICE_JOB, "before": started_before},
            )
            return [(row.job, row.run_key) for row in rows]

    async def stuck_job_runs(self, started_before: datetime) -> list[str]:
        async with self._engine.connect() as connection:
            rows = await connection.execute(
                STUCK_JOBS,
                {
                    "copy_job": COPY_JOB,
                    "notice_job": NOTICE_JOB,
                    "alert_job": ALERT_JOB,
                    "before": started_before,
                },
            )
            return [row.job for row in rows]

    async def schedule_rows(self, year: int) -> int:
        async with self._engine.connect() as connection:
            count: int = (await connection.execute(SCHEDULE_ROWS, {"year": year})).scalar_one()
            return count

    async def failed_runs_since(self, since: datetime) -> dict[str, int]:
        async with self._engine.connect() as connection:
            rows = await connection.execute(FAILED, {"since": since, "alert_job": ALERT_JOB})
            return {row.job: row.failures for row in rows}


class SqlAlertLog:
    """Records each alert in job_runs before it goes out (rule 12)."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def claim(self, key: str, now: datetime) -> bool:
        async with self._engine.begin() as connection:
            if not await claim_once(connection, ALERT_JOB, key, None, now):
                return False
            await finish_run(connection, ALERT_JOB, key, None, now)
            return True
