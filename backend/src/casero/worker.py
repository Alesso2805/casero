import asyncio
import contextlib
import signal
import sys
from collections.abc import Awaitable, Callable, Mapping
from datetime import date
from uuid import UUID

import asyncpg
import structlog
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from casero.admin.application.complaint_emails import (
    ComplaintMailer,
    ComplaintOutbox,
    SendComplaintEmails,
    SuppressedAddresses,
)
from casero.admin.domain.complaint_emails import BusinessIdentity, consumer_copy
from casero.admin.infrastructure.complaint_outbox import SqlComplaintOutbox
from casero.identity.infrastructure.email_suppressions import SuppressionLookup
from casero.leases.application.closing import CloseExpiredLeases, LeaseClosings
from casero.leases.infrastructure.closings import SqlLeaseClosings
from casero.ledger.application.charges import EnsureRentCharges, RentChargeStore
from casero.ledger.infrastructure.rent_charges import SqlRentCharges
from casero.shared.infrastructure.audit import SqlAuditLog
from casero.shared.infrastructure.database import create_engine
from casero.shared.infrastructure.error_tracking import init_error_tracking
from casero.shared.infrastructure.jobs import AccountWork, DailyAccountJob
from casero.shared.infrastructure.logs import configure_logging
from casero.shared.infrastructure.mail import SmtpMailer
from casero.shared.infrastructure.rate_limits import purge_expired_buckets
from casero.shared.infrastructure.settings import WorkerSettings
from casero.shared.kernel.audit import AuditLog
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


def account_jobs(clock: Clock) -> dict[str, AccountWork]:
    """Data jobs that bring each account up to the Lima day; leases close before charging."""

    async def close_leases(connection: AsyncConnection, account_id: UUID, today: date) -> None:
        closings: LeaseClosings = SqlLeaseClosings(connection)
        audit: AuditLog = SqlAuditLog(connection)
        await CloseExpiredLeases(closings, audit, clock)(account_id, today)

    async def rent_charges(connection: AsyncConnection, account_id: UUID, today: date) -> None:
        store: RentChargeStore = SqlRentCharges(connection)
        await EnsureRentCharges(store, clock)(account_id, today)

    return {"close_leases": close_leases, "rent_charges": rent_charges}


def build_jobs(settings: WorkerSettings, engine: AsyncEngine, clock: Clock) -> dict[str, Job]:
    outbox: ComplaintOutbox = SqlComplaintOutbox(engine)
    mailer: ComplaintMailer = SmtpMailer(settings.smtp, clock)
    suppressed: SuppressedAddresses = SuppressionLookup(engine, settings.email_hash_key)
    identity = business_identity(settings)

    async def purge_rate_limits() -> None:
        await purge_expired_buckets(engine, clock)

    return {
        "complaint_emails": SendComplaintEmails(outbox, mailer, suppressed, clock, identity),
        "rate_limit_purge": purge_rate_limits,
        **{
            name: DailyAccountJob(engine, clock, name, work)
            for name, work in account_jobs(clock).items()
        },
    }


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


async def serve(
    jobs: Mapping[str, Job], lock: asyncpg.Connection, stop: asyncio.Event, tick_seconds: int
) -> None:
    """Runs the jobs every tick until `stop` is set.

    A dropped lock connection releases the advisory lock, so the worker raises and lets the
    container restart instead of running beside another worker (rule 12).
    """
    while not stop.is_set():
        await lock.fetchval("SELECT 1")
        await run_jobs(jobs)
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), tick_seconds)


async def run() -> None:
    settings = WorkerSettings.from_environment()
    init_error_tracking(settings.sentry_dsn, settings.sentry_environment)
    clock: Clock = SystemClock()
    lock = await asyncpg.connect(settings.database_url)
    engine = create_engine(settings.engine_url)
    stop = asyncio.Event()
    with contextlib.suppress(NotImplementedError):
        asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, stop.set)
    try:
        if not await acquire_worker_lock(lock):
            log.info("worker.lock_held_elsewhere")
            return
        jobs = build_jobs(settings, engine, clock)
        log.info("worker.started", jobs=sorted(jobs))
        await serve(jobs, lock, stop, TICK_SECONDS)
        log.info("worker.stopped")
    finally:
        await engine.dispose()
        await lock.close()


def main() -> None:
    configure_logging()
    if sys.argv[1:2] == ["complaint-copy"] and len(sys.argv) == 3:
        sys.exit(asyncio.run(print_complaint_copy(sys.argv[2])))
    asyncio.run(run())


if __name__ == "__main__":
    main()
