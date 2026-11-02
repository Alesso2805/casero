import asyncio
import contextlib
import getpass
import os
import signal
import sys
from collections.abc import Awaitable, Callable, Mapping
from datetime import date, datetime, timedelta
from uuid import UUID

import asyncpg
import httpx2
import structlog
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from casero.accounts.application.entitlements import GetEntitlements
from casero.accounts.application.profile import Profiles
from casero.accounts.application.purge import ObjectStore, PurgeAccount, PurgeRecords
from casero.accounts.infrastructure.account import SqlPlans, SqlProfiles, SqlSubscriptions
from casero.accounts.infrastructure.purge import NoObjectStore, SqlPurgeRecords
from casero.admin.api.complaints import FileComplaintRequest
from casero.admin.application.alerts import AlertLog, AlertMailer, OpsReadings, RaiseAlerts
from casero.admin.application.complaint_commands import (
    ComplaintResponses,
    RegisterComplaint,
    RespondToComplaint,
    ResponseMailer,
    ResponseOutcome,
    StaffActions,
)
from casero.admin.application.complaint_emails import (
    ComplaintMailer,
    ComplaintOutbox,
    SendComplaintEmails,
    SuppressedAddresses,
)
from casero.admin.application.complaints import ComplaintRepository
from casero.admin.application.retention import ForgetExpiredData, RetentionStore
from casero.admin.application.staff import (
    CreateStaff,
    CreateStaffOutcome,
    RecoveryCodes,
    SecondFactor,
    StaffDirectory,
)
from casero.admin.domain.complaint_emails import BusinessIdentity, consumer_copy
from casero.admin.infrastructure.alerts import SqlAlertLog, SqlOpsReadings
from casero.admin.infrastructure.complaint_commands import (
    SqlComplaintResponses,
    SqlStaffActions,
)
from casero.admin.infrastructure.complaint_outbox import SqlComplaintOutbox
from casero.admin.infrastructure.complaints import SqlComplaintRepository
from casero.admin.infrastructure.retention import SqlRetention
from casero.admin.infrastructure.staff import (
    HashedRecoveryCodes,
    PyotpSecondFactor,
    SqlStaffDirectory,
)
from casero.identity.application.sessions import PasswordHasher
from casero.identity.application.users import MIN_PASSWORD_LENGTH
from casero.identity.infrastructure.email_suppressions import (
    SqlSuppressionStore,
    SuppressionLookup,
)
from casero.identity.infrastructure.passwords import Argon2PasswordHasher
from casero.identity.infrastructure.unsubscribe import HmacUnsubscribeTokens, UnsubscribeLinkMaker
from casero.leases.application.closing import CloseExpiredLeases, LeaseClosings
from casero.leases.application.leases import LeaseStore
from casero.leases.application.renters import RenterDocuments
from casero.leases.application.tools import EnsureLeaseTools, LeaseToolsStore
from casero.leases.infrastructure.closings import SqlLeaseClosings
from casero.leases.infrastructure.leases import SqlLeaseStore
from casero.leases.infrastructure.renters import SqlRenterHolders
from casero.leases.infrastructure.tools import SqlLeaseTools
from casero.ledger.application.charges import EnsureRentCharges, RentChargeStore
from casero.ledger.application.collections import CollectionsStore
from casero.ledger.infrastructure.ledger import SqlLedger
from casero.ledger.infrastructure.rent_charges import SqlRentCharges
from casero.properties.application.properties import PropertyStore
from casero.properties.infrastructure.properties import SqlPropertyStore
from casero.reminders.application.tax_reminders import (
    AccountOwner,
    SendTaxReminders,
    Suppressions,
    TaxReminderLog,
    TaxReminderMailer,
    UnsubscribeLinks,
)
from casero.reminders.application.trial_end import (
    BouncedAddresses,
    SendTrialEnded,
    TrialEmailLog,
)
from casero.reminders.infrastructure.reminders import SqlReminderLog
from casero.reminders.infrastructure.tax_reminders import SqlAccountOwner
from casero.reminders.infrastructure.trial_end import SqlTrialEmailLog
from casero.shared.infrastructure.audit import SqlAuditLog
from casero.shared.infrastructure.crypto import FieldCipher
from casero.shared.infrastructure.database import create_engine
from casero.shared.infrastructure.error_tracking import init_error_tracking
from casero.shared.infrastructure.jobs import AccountWork, DailyAccountJob
from casero.shared.infrastructure.logs import configure_logging
from casero.shared.infrastructure.mail import SmtpMailer
from casero.shared.infrastructure.rate_limits import purge_expired_buckets
from casero.shared.infrastructure.settings import (
    WorkerSettings,
    field_cipher_from_environment,
    smtp_from_environment,
)
from casero.shared.kernel.audit import AuditLog
from casero.shared.kernel.clock import LIMA, Clock, SystemClock
from casero.tax.application.calculator import TaxRuleBook
from casero.tax.application.declarations import GetDeclarations
from casero.tax.application.sunat_payments import TaxPaymentStore
from casero.tax.application.upcoming import GetPendingDues
from casero.tax.infrastructure.payments import SqlTaxPayments
from casero.tax.infrastructure.rule_book import SqlTaxRuleBook

WORKER_LOCK_KEY = 7_294_011
TICK_SECONDS = 60
HEARTBEAT_TIMEOUT_SECONDS = 10
TAX_REMINDERS_FROM_HOUR = 8
# A failed account is retried 3 times a day (rule 12); an hour apart, a short SMTP outage
# doesn't use them all.
TAX_REMINDER_RETRY_EVERY = timedelta(hours=1)
RETENTION_EVERY = timedelta(hours=1)

type Job = Callable[[], Awaitable[None]]
type Heartbeat = Callable[[], Awaitable[None]]

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

    async def lease_tools(connection: AsyncConnection, account_id: UUID, _: date) -> None:
        entitlements = GetEntitlements(SqlSubscriptions(connection), SqlPlans(connection), clock)
        store: LeaseToolsStore = SqlLeaseTools(connection)
        audit: AuditLog = SqlAuditLog(connection)
        await EnsureLeaseTools(entitlements, store, audit, clock)(account_id)

    return {
        "close_leases": close_leases,
        "rent_charges": rent_charges,
        "lease_tools": lease_tools,
    }


def purge_work(clock: Clock) -> AccountWork:
    objects: ObjectStore = NoObjectStore()

    async def purge(connection: AsyncConnection, account_id: UUID, today: date) -> None:
        records: PurgeRecords = SqlPurgeRecords(connection)
        await PurgeAccount(records, objects, clock)(account_id, today)

    return purge


def declarations_in(
    connection: AsyncConnection, entitlements: GetEntitlements, clock: Clock
) -> GetDeclarations:
    profiles: Profiles = SqlProfiles(connection)
    properties: PropertyStore = SqlPropertyStore(connection)
    leases: LeaseStore = SqlLeaseStore(connection)
    renters: RenterDocuments = SqlRenterHolders(connection)
    books: CollectionsStore = SqlLedger(connection)
    rule_book: TaxRuleBook = SqlTaxRuleBook(connection)
    tax_payments: TaxPaymentStore = SqlTaxPayments(connection)
    return GetDeclarations(
        entitlements, profiles, properties, leases, renters, books, rule_book, tax_payments, clock
    )


def trial_ended_work(settings: WorkerSettings, engine: AsyncEngine, clock: Clock) -> AccountWork:
    mailer: TaxReminderMailer = SmtpMailer(settings.smtp, clock)
    bounced: BouncedAddresses = SuppressionLookup(engine, settings.email_hash_key)
    log: TrialEmailLog = SqlTrialEmailLog(engine)

    async def send(connection: AsyncConnection, account_id: UUID, today: date) -> None:
        entitlements = GetEntitlements(SqlSubscriptions(connection), SqlPlans(connection), clock)
        profiles: Profiles = SqlProfiles(connection)
        rule_book: TaxRuleBook = SqlTaxRuleBook(connection)
        owner: AccountOwner = SqlAccountOwner(connection)
        declarations = declarations_in(connection, entitlements, clock)
        await SendTrialEnded(
            entitlements,
            profiles,
            GetPendingDues(declarations, profiles, rule_book, clock),
            owner,
            bounced,
            log,
            mailer,
            settings.public_url,
            clock,
        )(account_id, today)

    return send


def tax_reminder_work(settings: WorkerSettings, clock: Clock) -> AccountWork:
    mailer: TaxReminderMailer = SmtpMailer(settings.smtp, clock)
    unsubscribe: UnsubscribeLinks = UnsubscribeLinkMaker(
        settings.public_url, HmacUnsubscribeTokens(settings.unsubscribe_key)
    )

    async def send(connection: AsyncConnection, account_id: UUID, today: date) -> None:
        entitlements = GetEntitlements(SqlSubscriptions(connection), SqlPlans(connection), clock)
        profiles: Profiles = SqlProfiles(connection)
        rule_book: TaxRuleBook = SqlTaxRuleBook(connection)
        owner: AccountOwner = SqlAccountOwner(connection)
        suppressions: Suppressions = SqlSuppressionStore(connection, settings.email_hash_key)
        log: TaxReminderLog = SqlReminderLog(connection)
        declarations = declarations_in(connection, entitlements, clock)
        await SendTaxReminders(
            entitlements,
            profiles,
            rule_book,
            declarations,
            owner,
            suppressions,
            unsubscribe,
            log,
            mailer,
            settings.public_url,
            clock,
        )(account_id, today)

    return send


def from_lima_hour(hour: int, clock: Clock, job: Job) -> Job:
    """Emails wait for the morning in Lima instead of going out at midnight."""

    async def gated() -> None:
        if clock.now().astimezone(LIMA).hour >= hour:
            await job()

    return gated


def at_most_every(interval: timedelta, clock: Clock, job: Job) -> Job:
    started: list[datetime] = []

    async def spaced() -> None:
        now = clock.now()
        if started and now - started[-1] < interval:
            return
        started[:] = [now]
        await job()

    return spaced


def build_jobs(settings: WorkerSettings, engine: AsyncEngine, clock: Clock) -> dict[str, Job]:
    outbox: ComplaintOutbox = SqlComplaintOutbox(engine)
    mailer: ComplaintMailer = SmtpMailer(settings.smtp, clock)
    suppressed: SuppressedAddresses = SuppressionLookup(engine, settings.email_hash_key)
    identity = business_identity(settings)
    readings: OpsReadings = SqlOpsReadings(engine)
    alert_log: AlertLog = SqlAlertLog(engine)
    alert_mailer: AlertMailer = SmtpMailer(settings.smtp, clock)
    retention: RetentionStore = SqlRetention(engine)

    async def purge_rate_limits() -> None:
        await purge_expired_buckets(engine, clock)

    return {
        "complaint_emails": SendComplaintEmails(outbox, mailer, suppressed, clock, identity),
        "rate_limit_purge": purge_rate_limits,
        "retention": at_most_every(RETENTION_EVERY, clock, ForgetExpiredData(retention, clock)),
        "alerts": RaiseAlerts(readings, alert_log, alert_mailer, settings.alerts_inbox, clock),
        **{
            name: DailyAccountJob(engine, clock, name, work)
            for name, work in account_jobs(clock).items()
        },
        "purge_accounts": DailyAccountJob(
            engine, clock, "purge_accounts", purge_work(clock), purpose="purge"
        ),
        "trial_ended_emails": from_lima_hour(
            TAX_REMINDERS_FROM_HOUR,
            clock,
            DailyAccountJob(
                engine, clock, "trial_ended_emails", trial_ended_work(settings, engine, clock)
            ),
        ),
        "tax_reminders": from_lima_hour(
            TAX_REMINDERS_FROM_HOUR,
            clock,
            at_most_every(
                TAX_REMINDER_RETRY_EVERY,
                clock,
                DailyAccountJob(engine, clock, "tax_reminders", tax_reminder_work(settings, clock)),
            ),
        ),
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


RESPONSE_MESSAGES: dict[ResponseOutcome, str] = {
    "responded": "Listo: la respuesta quedó registrada.",
    "not_found": "No hay un reclamo con ese número.",
    "already_responded": "Ese reclamo ya tiene respuesta.",
    "needs_sent_on": "Es una respuesta por carta: indica SENT_ON con la fecha de envío.",
    "email_failed": "No se pudo enviar el correo, así que no se registró nada.",
}


async def respond_to_complaint(
    database_url: str,
    mailer: ResponseMailer,
    complaints_inbox: str,
    clock: Clock,
    number: str,
    text: str,
    sent_on: date | None,
) -> ResponseOutcome:
    """casero_admin answers: the panel's role, with a grant only on these columns."""
    engine = create_engine(database_url)
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            responses: ComplaintResponses = SqlComplaintResponses(connection)
            actions: StaffActions = SqlStaffActions(connection)
            respond = RespondToComplaint(responses, mailer, actions, complaints_inbox, clock)
            outcome = await respond(number, text, sent_on)
            await (transaction.commit() if outcome == "responded" else transaction.rollback())
            return outcome
    finally:
        await engine.dispose()


async def register_complaint(
    database_url: str, clock: Clock, sheet_json: str, filed_at: datetime
) -> str:
    """As casero_owner, like load-tax-config: casero_admin stays without INSERT on complaints."""
    sheet = FileComplaintRequest.model_validate_json(sheet_json).to_sheet()
    engine = create_engine(database_url)
    try:
        async with engine.begin() as connection:
            repository: ComplaintRepository = SqlComplaintRepository(connection)
            actions: StaffActions = SqlStaffActions(connection)
            complaint = await RegisterComplaint(repository, actions, clock)(sheet, filed_at)
            return complaint.number
    finally:
        await engine.dispose()


async def create_staff(
    database_url: str, cipher: FieldCipher, clock: Clock, email: str, password: str
) -> CreateStaffOutcome:
    """As casero_owner and never over HTTP (ADR-0008): the panel's role can't write staff_users."""
    engine = create_engine(database_url)
    try:
        async with engine.begin() as connection:
            directory: StaffDirectory = SqlStaffDirectory(connection, cipher)
            passwords: PasswordHasher = Argon2PasswordHasher()
            second_factor: SecondFactor = PyotpSecondFactor()
            recovery_codes: RecoveryCodes = HashedRecoveryCodes()
            actions: StaffActions = SqlStaffActions(connection)
            create = CreateStaff(
                directory, passwords, second_factor, recovery_codes, actions, clock
            )
            return await create(email, password)
    finally:
        await engine.dispose()


def staff_command(arguments: list[str]) -> int:
    """`create-staff EMAIL`. The password is typed, so it stays out of the shell history."""
    if len(arguments) != 2 or "@" not in arguments[1]:
        print("Uso: make create-staff EMAIL=correo@ejemplo.com", file=sys.stderr)
        return 2
    password = getpass.getpass("Contraseña: ")
    if password != getpass.getpass("Repite la contraseña: "):
        print("Las contraseñas no coinciden.", file=sys.stderr)
        return 1
    outcome = asyncio.run(
        create_staff(
            os.environ["CASERO_MIGRATION_DATABASE_URL"],
            field_cipher_from_environment(os.environ),
            SystemClock(),
            arguments[1].strip(),
            password,
        )
    )
    if outcome == "email_taken":
        print("Ese correo ya tiene una cuenta de personal.", file=sys.stderr)
        return 1
    if outcome == "weak_password":
        print(f"Usa al menos {MIN_PASSWORD_LENGTH} caracteres.", file=sys.stderr)
        return 1
    print("Listo. Agrega este enlace a tu app de autenticación:")
    print(outcome.totp_uri)
    print("Guarda estos códigos en Bitwarden. Cada uno sirve una vez y no se vuelven a mostrar:")
    print("\n".join(outcome.recovery_codes))
    return 0


def lima_moment(text: str) -> datetime:
    moment = datetime.fromisoformat(text)
    return moment if moment.tzinfo else moment.replace(tzinfo=LIMA)


def complaint_command(arguments: list[str]) -> int:
    """`complaint-respond NUMBER [SENT_ON]` and `complaint-register FILED_AT`, reading stdin."""
    clock = SystemClock()
    if arguments[0] == "complaint-register" and len(arguments) == 2:
        number = asyncio.run(
            register_complaint(
                os.environ["CASERO_MIGRATION_DATABASE_URL"],
                clock,
                sys.stdin.read(),
                lima_moment(arguments[1]),
            )
        )
        print(f"Listo: quedó registrado con el número {number}.")
        return 0
    if arguments[0] == "complaint-respond" and len(arguments) in (2, 3):
        mailer: ResponseMailer = SmtpMailer(smtp_from_environment(os.environ), clock)
        outcome = asyncio.run(
            respond_to_complaint(
                os.environ["CASERO_ADMIN_DATABASE_URL"],
                mailer,
                os.environ["CASERO_COMPLAINTS_INBOX"],
                clock,
                arguments[1],
                sys.stdin.read().strip(),
                date.fromisoformat(arguments[2]) if len(arguments) == 3 else None,
            )
        )
        print(RESPONSE_MESSAGES[outcome], file=sys.stdout if outcome == "responded" else sys.stderr)
        return 0 if outcome == "responded" else 1
    print("Uso: docs/ops/complaints.md", file=sys.stderr)
    return 2


async def run_jobs(jobs: Mapping[str, Job]) -> bool:
    """True when every job ran without crashing."""
    healthy = True
    for name, job in jobs.items():
        try:
            await job()
        except Exception as error:
            # Only the type: exception messages can carry personal data (CLAUDE.md, rule 8).
            log.error("worker.job_crashed", job=name, error=type(error).__name__)
            healthy = False
    return healthy


def heartbeat_to(url: str | None) -> Heartbeat:
    """Pings the monitor, which alerts when the pings stop (docs/ops/backups.md)."""

    async def beat() -> None:
        if url is None:
            return
        try:
            async with httpx2.AsyncClient(timeout=HEARTBEAT_TIMEOUT_SECONDS) as client:
                (await client.get(url)).raise_for_status()
        except httpx2.HTTPError as error:
            log.warning("worker.heartbeat_failed", error=type(error).__name__)

    return beat


async def serve(
    jobs: Mapping[str, Job],
    lock: asyncpg.Connection,
    stop: asyncio.Event,
    tick_seconds: int,
    heartbeat: Heartbeat,
) -> None:
    """Runs the jobs every tick until `stop` is set, with a heartbeat after each healthy tick.

    A dropped lock connection releases the advisory lock, so the worker raises and lets the
    container restart instead of running beside another worker (rule 12).
    """
    while not stop.is_set():
        await lock.fetchval("SELECT 1")
        if await run_jobs(jobs):
            await heartbeat()
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
            log.error("worker.lock_held_elsewhere")
            return
        jobs = build_jobs(settings, engine, clock)
        log.info("worker.started", jobs=sorted(jobs))
        await serve(jobs, lock, stop, TICK_SECONDS, heartbeat_to(settings.heartbeat_url))
        log.info("worker.stopped")
    finally:
        await engine.dispose()
        await lock.close()


def main() -> None:
    configure_logging()
    if sys.argv[1:2] == ["complaint-copy"] and len(sys.argv) == 3:
        sys.exit(asyncio.run(print_complaint_copy(sys.argv[2])))
    if sys.argv[1:2] in (["complaint-respond"], ["complaint-register"]):
        sys.exit(complaint_command(sys.argv[1:]))
    if sys.argv[1:2] == ["create-staff"]:
        sys.exit(staff_command(sys.argv[1:]))
    asyncio.run(run())


if __name__ == "__main__":
    main()
