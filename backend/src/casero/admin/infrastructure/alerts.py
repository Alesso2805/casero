from datetime import date, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from casero.admin.application.alerts import UnansweredComplaint
from casero.admin.application.complaint_emails import COPY_JOB, NOTICE_JOB
from casero.shared.infrastructure.jobs import claim_once, finish_run
from casero.shared.kernel.clock import LIMA

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
TAX_RULES = text("SELECT EXISTS (SELECT 1 FROM tax_rule_sets WHERE year = :year)")
FAILED = text(
    "SELECT job, count(*) AS failures FROM job_runs WHERE status = 'failed'"
    " AND finished_at >= :since AND job <> :alert_job GROUP BY job"
)
UNANSWERED = text(
    "SELECT number, created_at, due_at FROM complaints WHERE responded_at IS NULL"
    " ORDER BY created_at"
)
HOLIDAYS_AFTER = text("SELECT date FROM holidays WHERE date > :day")


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

    async def has_tax_rules(self, year: int) -> bool:
        async with self._engine.connect() as connection:
            found: bool = (await connection.execute(TAX_RULES, {"year": year})).scalar_one()
            return found

    async def failed_runs_since(self, since: datetime) -> dict[str, int]:
        async with self._engine.connect() as connection:
            rows = await connection.execute(FAILED, {"since": since, "alert_job": ALERT_JOB})
            return {row.job: row.failures for row in rows}

    async def unanswered_complaints(self) -> list[UnansweredComplaint]:
        async with self._engine.connect() as connection:
            rows = await connection.execute(UNANSWERED)
            return [
                UnansweredComplaint(row.number, row.created_at.astimezone(LIMA).date(), row.due_at)
                for row in rows
            ]

    async def holidays_after(self, day: date) -> frozenset[date]:
        async with self._engine.connect() as connection:
            rows = await connection.execute(HOLIDAYS_AFTER, {"day": day})
            return frozenset(row.date for row in rows)


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
