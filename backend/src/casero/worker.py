import asyncio
from collections.abc import Awaitable, Callable, Mapping

import asyncpg
import structlog
from sqlalchemy.ext.asyncio import AsyncEngine

from casero.admin.application.complaint_emails import (
    ComplaintMailer,
    ComplaintOutbox,
    SendComplaintEmails,
)
from casero.admin.domain.complaint_emails import BusinessIdentity
from casero.admin.infrastructure.complaint_outbox import SqlComplaintOutbox
from casero.shared.infrastructure.database import create_engine
from casero.shared.infrastructure.mail import SmtpMailer
from casero.shared.infrastructure.settings import WorkerSettings
from casero.shared.kernel.clock import Clock, SystemClock

WORKER_LOCK_KEY = 7_294_011
TICK_SECONDS = 60

type Job = Callable[[], Awaitable[None]]

log = structlog.get_logger()


async def acquire_worker_lock(connection: asyncpg.Connection) -> bool:
    acquired: bool = await connection.fetchval("SELECT pg_try_advisory_lock($1)", WORKER_LOCK_KEY)
    return acquired


def build_jobs(settings: WorkerSettings, engine: AsyncEngine, clock: Clock) -> dict[str, Job]:
    outbox: ComplaintOutbox = SqlComplaintOutbox(engine)
    mailer: ComplaintMailer = SmtpMailer(settings.smtp, clock)
    business = settings.business
    identity = BusinessIdentity(
        name=business.name,
        ruc=business.ruc,
        address=business.address,
        complaints_inbox=business.complaints_inbox,
    )
    return {"complaint_emails": SendComplaintEmails(outbox, mailer, clock, identity)}


async def run_jobs(jobs: Mapping[str, Job]) -> None:
    for name, job in jobs.items():
        try:
            await job()
        except Exception as error:
            # Only the type: exception messages can carry personal data (CLAUDE.md, rule 8).
            log.error("worker.job_crashed", job=name, error=type(error).__name__)


async def run() -> None:
    settings = WorkerSettings.from_environment()
    clock: Clock = SystemClock()
    lock = await asyncpg.connect(settings.database_url)
    engine = create_engine(settings.engine_url)
    try:
        if not await acquire_worker_lock(lock):
            log.info("worker.lock_held_elsewhere")
            return
        jobs = build_jobs(settings, engine, clock)
        log.info("worker.started", jobs=sorted(jobs))
        while True:
            await run_jobs(jobs)
            await asyncio.sleep(TICK_SECONDS)
    finally:
        await engine.dispose()
        await lock.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
