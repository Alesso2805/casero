from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid7

import asyncpg
import pytest
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from api_client import TEST_EMAIL_HASH_KEY, FixedClock, RecordingMailer
from casero.accounts.application.entitlements import GetEntitlements
from casero.accounts.infrastructure.account import SqlPlans, SqlProfiles, SqlSubscriptions
from casero.identity.infrastructure.email_suppressions import SuppressionLookup, email_hash
from casero.leases.infrastructure.leases import SqlLeaseStore
from casero.leases.infrastructure.renters import SqlRenterHolders
from casero.ledger.infrastructure.ledger import SqlLedger
from casero.properties.infrastructure.properties import SqlPropertyStore
from casero.reminders.application.trial_end import SendTrialEnded
from casero.reminders.infrastructure.tax_reminders import SqlAccountOwner
from casero.reminders.infrastructure.trial_end import SqlTrialEmailLog
from casero.shared.infrastructure.database import create_engine, set_account_context
from casero.tax.application.declarations import GetDeclarations
from casero.tax.application.upcoming import GetPendingDues
from casero.tax.infrastructure.payments import SqlTaxPayments
from casero.tax.infrastructure.rule_book import SqlTaxRuleBook
from database import Database
from tax_flows import add_renter, client_for, pay, register, save_ruc, start_leases

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 27, 15, 0, tzinfo=UTC)
TRIAL_ENDS = date(2026, 11, 10)
APP_URL = "https://casero.example"


@pytest.fixture
async def engine(database: Database) -> AsyncIterator[AsyncEngine]:
    worker = create_engine(
        database.dsn("casero_worker").replace("postgresql://", "postgresql+asyncpg://", 1)
    )
    try:
        yield worker
    finally:
        await worker.dispose()


async def owner_run(database: Database, query: str, *args: object) -> list[asyncpg.Record]:
    owner = await asyncpg.connect(database.dsn("casero_owner"))
    try:
        return await owner.fetch(query, *args)
    finally:
        await owner.close()


async def landlord(
    database: Database, request: pytest.FixtureRequest, *, verified: bool = True
) -> tuple[UUID, str]:
    email = f"{uuid7()}@example.com"
    with client_for(database, request, FixedClock(NOW)) as client:
        register(client, email)
        save_ruc(client)
        ana = add_renter(client, "Ana", {"doc_type": "dni", "number": "45678912"})
        [lease] = start_leases(client, {"renter_id": ana})
        pay(client, lease, 80_000, "2026-10-05")
    [row] = await owner_run(
        database,
        "SELECT m.account_id FROM account_members m JOIN users u ON u.id = m.user_id"
        " WHERE u.email = $1",
        email,
    )
    await owner_run(
        database,
        "UPDATE subscriptions SET trial_ends_at = $2, ends_at = $2 WHERE account_id = $1",
        row["account_id"],
        TRIAL_ENDS,
    )
    if verified:
        await owner_run(
            database, "UPDATE users SET email_verified_at = $1 WHERE email = $2", NOW, email
        )
    account_id: UUID = row["account_id"]
    return account_id, email


def send_trial_ended(
    connection: AsyncConnection, engine: AsyncEngine, mailer: Any, today: date
) -> SendTrialEnded:
    clock = FixedClock(datetime(today.year, today.month, today.day, 15, 0, tzinfo=UTC))
    entitlements = GetEntitlements(SqlSubscriptions(connection), SqlPlans(connection), clock)
    rule_book = SqlTaxRuleBook(connection)
    declarations = GetDeclarations(
        entitlements,
        SqlProfiles(connection),
        SqlPropertyStore(connection),
        SqlLeaseStore(connection),
        SqlRenterHolders(connection),
        SqlLedger(connection),
        rule_book,
        SqlTaxPayments(connection),
        clock,
    )
    return SendTrialEnded(
        entitlements,
        SqlProfiles(connection),
        GetPendingDues(declarations, SqlProfiles(connection), rule_book, clock),
        SqlAccountOwner(connection),
        SuppressionLookup(engine, TEST_EMAIL_HASH_KEY),
        SqlTrialEmailLog(engine),
        mailer,
        APP_URL,
        clock,
    )


async def run_on(engine: AsyncEngine, account_id: UUID, mailer: Any, today: date) -> None:
    async with engine.begin() as connection:
        await set_account_context(connection, account_id)
        await send_trial_ended(connection, engine, mailer, today)(account_id, today)


async def test_the_end_of_the_trial_is_told_once_with_what_is_still_owed_to_sunat(
    database: Database, request: pytest.FixtureRequest, engine: AsyncEngine
) -> None:
    account_id, email = await landlord(database, request)
    mailer = RecordingMailer()

    await run_on(engine, account_id, mailer, date(2026, 11, 9))
    await run_on(engine, account_id, mailer, TRIAL_ENDS)
    await run_on(engine, account_id, mailer, date(2026, 11, 11))

    [sent] = mailer.sent
    assert (sent.to, sent.subject) == (email, "Terminó tu prueba de Casero")
    assert "terminó el 10/11/2026" in sent.text
    assert "hasta el 16/11/2026" in sent.text
    assert "octubre de 2026: S/ 40.00, vencen el 19/11/2026" in sent.text
    assert f"{APP_URL}/app/plan" in sent.text


async def test_after_the_grace_days_it_is_too_late_to_tell(
    database: Database, request: pytest.FixtureRequest, engine: AsyncEngine
) -> None:
    account_id, _ = await landlord(database, request)
    mailer = RecordingMailer()

    await run_on(engine, account_id, mailer, date(2026, 11, 17))

    assert mailer.sent == []


async def test_a_paid_subscription_gets_no_trial_email(
    database: Database, request: pytest.FixtureRequest, engine: AsyncEngine
) -> None:
    account_id, _ = await landlord(database, request)
    await owner_run(
        database,
        "UPDATE subscriptions SET ends_at = '2027-11-10' WHERE account_id = $1",
        account_id,
    )
    mailer = RecordingMailer()

    await run_on(engine, account_id, mailer, TRIAL_ENDS)

    assert mailer.sent == []


async def test_an_unverified_or_bouncing_address_gets_nothing(
    database: Database, request: pytest.FixtureRequest, engine: AsyncEngine
) -> None:
    unverified, _ = await landlord(database, request, verified=False)
    bouncing, email = await landlord(database, request)
    await owner_run(
        database,
        "INSERT INTO email_suppressions (email_hash, reason, created_at) VALUES ($1, 'bounce', $2)",
        email_hash(TEST_EMAIL_HASH_KEY, email),
        NOW,
    )
    mailer = RecordingMailer()

    await run_on(engine, unverified, mailer, TRIAL_ENDS)
    await run_on(engine, bouncing, mailer, TRIAL_ENDS)

    assert mailer.sent == []
