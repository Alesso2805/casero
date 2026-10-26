import asyncio
import sys
from collections.abc import Awaitable, Callable, Mapping

import asyncpg
import structlog
from sqlalchemy.ext.asyncio import AsyncEngine

from casero.admin.application.complaint_emails import (
    ComplaintMailer,
    ComplaintOutbox,
    SendComplaintEmails,
    SuppressedAddresses,
)
from casero.admin.domain.complaint_emails import BusinessIdentity, consumer_copy
from casero.admin.infrastructure.complaint_outbox import SqlComplaintOutbox
from casero.identity.infrastructure.email_suppressions import SuppressionLookup
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


def business_identity(settings: WorkerSettings) -> BusinessIdentity:
    business = settings.business
    return BusinessIdentity(
        name=business.name,
        ruc=business.ruc,
        address=business.address,
        complaints_inbox=settings.complaints_inbox,
    )


def build_jobs(settings: WorkerSettings, engine: AsyncEngine, clock: Clock) -> dict[str, Job]:
    outbox: ComplaintOutbox = SqlComplaintOutbox(engine)
    mailer: ComplaintMailer = SmtpMailer(settings.smtp, clock)
    suppressed: SuppressedAddresses = SuppressionLookup(engine, settings.email_hash_key)
    identity = business_identity(settings)
    return {"complaint_emails": SendComplaintEmails(outbox, mailer, suppressed, clock, identity)}


async def complaint_copy_text(
    engine: AsyncEngine, number: str, business: BusinessIdentity
) -> str | None:
    complaint = await SqlComplaintOutbox(engine).by_number(number)
    if complaint is None or complaint.sheet.email is None:
        return None
    email = consumer_copy(complaint, business)
    return f"Para: {email.to}\nAsunto: {email.subject}\n\n{email.text}"


async def print_complaint_copy(number: str) -> int:
    settings = WorkerSettings.from_environment()
    engine = create_engine(settings.engine_url)
    try:
        copy = await complaint_copy_text(engine, number, business_identity(settings))
    finally:
        await engine.dispose()
    if copy is None:
        print(f"No hay un reclamo {number} con correo del consumidor.", file=sys.stderr)
        return 1
    print(copy)
    return 0


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
    if sys.argv[1:2] == ["complaint-copy"] and len(sys.argv) == 3:
        sys.exit(asyncio.run(print_complaint_copy(sys.argv[2])))
    asyncio.run(run())


if __name__ == "__main__":
    main()
