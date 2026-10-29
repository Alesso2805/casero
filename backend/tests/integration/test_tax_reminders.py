from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from urllib.parse import urlsplit
from uuid import UUID, uuid7

import asyncpg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from api_client import TEST_EMAIL_HASH_KEY, TEST_UNSUBSCRIBE_KEY, FixedClock, RecordingMailer
from casero.accounts.application.entitlements import GetEntitlements
from casero.accounts.infrastructure.account import SqlPlans, SqlProfiles, SqlSubscriptions
from casero.identity.domain.email_suppressions import (
    ScheduledEmailKind,
    Suppression,
    SuppressionReason,
)
from casero.identity.infrastructure.email_suppressions import SqlSuppressionStore
from casero.identity.infrastructure.unsubscribe import HmacUnsubscribeTokens, UnsubscribeLinkMaker
from casero.leases.infrastructure.leases import SqlLeaseStore
from casero.leases.infrastructure.renters import SqlRenterHolders
from casero.ledger.infrastructure.ledger import SqlLedger
from casero.properties.infrastructure.properties import SqlPropertyStore
from casero.reminders.application.tax_reminders import SendTaxReminders
from casero.reminders.infrastructure.reminders import SqlReminderLog
from casero.reminders.infrastructure.tax_reminders import SqlAccountOwner
from casero.shared.infrastructure.database import create_engine, set_account_context
from casero.shared.infrastructure.mail import SmtpMailer, SmtpSettings
from casero.shared.kernel.email import Email, MailDeliveryError
from casero.tax.application.declarations import GetDeclarations
from casero.tax.infrastructure.payments import SqlTaxPayments
from casero.tax.infrastructure.rule_book import SqlTaxRuleBook
from database import Database
from tax_flows import add_renter, client_for, pay, register, save_ruc, send, start_leases

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 27, 15, 0, tzinfo=UTC)
FIVE_DAYS_BEFORE = date(2026, 11, 14)
APP_URL = "https://casero.example"
SMTP = SmtpSettings("smtp.invalid", 25, "none", None, None, "Casero <no-reply@example.com>")


class FailingMailer:
    async def send(self, email: Email) -> None:
        raise MailDeliveryError("SMTPServerDisconnected")


def reminders_with(
    connection: AsyncConnection, mailer: RecordingMailer | FailingMailer, today: date
) -> SendTaxReminders:
    clock = FixedClock(datetime(today.year, today.month, today.day, 13, 0, tzinfo=UTC))
    entitlements = GetEntitlements(SqlSubscriptions(connection), SqlPlans(connection), clock)
    declarations = GetDeclarations(
        entitlements,
        SqlProfiles(connection),
        SqlPropertyStore(connection),
        SqlLeaseStore(connection),
        SqlRenterHolders(connection),
        SqlLedger(connection),
        SqlTaxRuleBook(connection),
        SqlTaxPayments(connection),
        clock,
    )
    return SendTaxReminders(
        entitlements,
        SqlProfiles(connection),
        SqlTaxRuleBook(connection),
        declarations,
        SqlAccountOwner(connection),
        SqlSuppressionStore(connection, TEST_EMAIL_HASH_KEY),
        UnsubscribeLinkMaker(APP_URL, HmacUnsubscribeTokens(TEST_UNSUBSCRIBE_KEY)),
        SqlReminderLog(connection),
        mailer,
        APP_URL,
        clock,
    )


@pytest.fixture
async def worker_engine(database: Database) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(
        database.dsn("casero_worker").replace("postgresql://", "postgresql+asyncpg://", 1)
    )
    yield engine
    await engine.dispose()


async def owner_rows(database: Database, query: str, *args: object) -> list[asyncpg.Record]:
    owner = await asyncpg.connect(database.dsn("casero_owner"))
    try:
        return await owner.fetch(query, *args)
    finally:
        await owner.close()


async def landlord_owing_october(
    database: Database, client: TestClient, *, ruc: bool = True, verified: bool = True
) -> tuple[UUID, str, str]:
    email = f"{uuid7()}@example.com"
    register(client, email)
    if ruc:
        save_ruc(client)
    ana = add_renter(client, "Ana Quispe", {"doc_type": "dni", "number": "45678912"})
    rosa = add_renter(client, "Rosa Huamán")
    ana_lease, rosa_lease = start_leases(client, {"renter_id": ana}, {"renter_id": rosa})
    pay(client, ana_lease, 56_000, "2026-10-05")
    pay(client, rosa_lease, 30_000, "2026-10-06")
    if verified:
        await owner_rows(
            database, "UPDATE users SET email_verified_at = $1 WHERE email = $2", NOW, email
        )
    [row] = await owner_rows(
        database,
        "SELECT m.account_id FROM account_members m JOIN users u ON u.id = m.user_id"
        " WHERE u.email = $1",
        email,
    )
    return row["account_id"], email, ana


async def run_for(
    engine: AsyncEngine,
    account_id: UUID,
    today: date,
    mailer: RecordingMailer | FailingMailer,
) -> None:
    async with engine.begin() as connection:
        await set_account_context(connection, account_id)
        await reminders_with(connection, mailer, today)(account_id, today)


async def logged(database: Database, account_id: UUID) -> list[tuple[str, str, str, bool]]:
    rows = await owner_rows(
        database,
        "SELECT g.kind, g.channel, g.period, g.renter_doc_hmac IS NULL AS no_document"
        " FROM reminder_logs g WHERE g.account_id = $1 ORDER BY g.renter_doc_hmac NULLS LAST",
        account_id,
    )
    return [(r["kind"], r["channel"], r["period"], r["no_document"]) for r in rows]


async def test_five_days_and_one_day_before_it_emails_what_is_owed(
    database: Database, request: pytest.FixtureRequest, worker_engine: AsyncEngine
) -> None:
    with client_for(database, request, FixedClock(NOW)) as client:
        account_id, email, _ = await landlord_owing_october(database, client)
    mailer = RecordingMailer()

    for today in (date(2026, 11, 13), FIVE_DAYS_BEFORE, date(2026, 11, 18), date(2026, 11, 19)):
        await run_for(worker_engine, account_id, today, mailer)

    assert [(sent.to, sent.subject) for sent in mailer.sent] == [
        (email, "Tus formularios 1683 de octubre de 2026 vencen el 19/11/2026"),
        (email, "Mañana vencen tus formularios 1683 de octubre de 2026"),
    ]
    first = mailer.sent[0]
    assert "- Ana Quispe: S/ 28.00" in first.text
    assert "- Rosa Huamán: S/ 15.00. Falta su documento" in first.text
    assert first.unsubscribe_url is not None
    assert first.unsubscribe_url.startswith(f"{APP_URL}/api/public/unsubscribe?")
    assert "45678912" not in first.text
    assert await logged(database, account_id) == [
        ("tax_due", "email", "2026-10", False),
        ("tax_due", "email", "2026-10", False),
        ("tax_due", "email", "2026-10", True),
        ("tax_due", "email", "2026-10", True),
    ]


@pytest.mark.parametrize("new_document", [False, True])
async def test_what_was_paid_to_sunat_is_left_out(
    database: Database,
    request: pytest.FixtureRequest,
    worker_engine: AsyncEngine,
    new_document: bool,
) -> None:
    with client_for(database, request, FixedClock(NOW)) as client:
        account_id, _, ana = await landlord_owing_october(database, client)
        body = {
            "id": str(uuid7()),
            "period": "2026-10",
            "renter_id": ana,
            "amount_cents": 2_800,
            "paid_on": "2026-10-27",
            "order_number": "1234567890",
            "declared_base_cents": 56_000,
        }
        assert send(client, "POST", "/api/app/tax/payments", body).status_code == 201
        if new_document:
            ana_ce = {"doc_type": "ce", "number": "001234567"}
            renter = {"full_name": "Ana Quispe", "document": ana_ce}
            assert send(client, "PUT", f"/api/app/renters/{ana}", renter).status_code == 200
    mailer = RecordingMailer()

    await run_for(worker_engine, account_id, FIVE_DAYS_BEFORE, mailer)

    [sent] = mailer.sent
    assert "Ana Quispe" not in sent.text
    assert "Total: S/ 15.00" in sent.text


@pytest.mark.parametrize(("kind", "reason"), [("tax_reminders", "unsubscribe"), (None, "bounce")])
async def test_an_unsubscribed_or_bouncing_address_gets_nothing(
    database: Database,
    request: pytest.FixtureRequest,
    worker_engine: AsyncEngine,
    kind: ScheduledEmailKind | None,
    reason: SuppressionReason,
) -> None:
    with client_for(database, request, FixedClock(NOW)) as client:
        account_id, email, _ = await landlord_owing_october(database, client)
    async with worker_engine.begin() as connection:
        await SqlSuppressionStore(connection, TEST_EMAIL_HASH_KEY).add(
            Suppression(email, kind, reason), NOW
        )
    mailer = RecordingMailer()

    await run_for(worker_engine, account_id, FIVE_DAYS_BEFORE, mailer)

    assert mailer.sent == []
    assert await logged(database, account_id) == []


@pytest.mark.parametrize(("ruc", "verified"), [(False, True), (True, False)])
async def test_without_a_ruc_or_a_verified_email_nothing_is_sent(
    database: Database,
    request: pytest.FixtureRequest,
    worker_engine: AsyncEngine,
    ruc: bool,
    verified: bool,
) -> None:
    with client_for(database, request, FixedClock(NOW)) as client:
        account_id, _, _ = await landlord_owing_october(
            database, client, ruc=ruc, verified=verified
        )
    mailer = RecordingMailer()

    await run_for(worker_engine, account_id, FIVE_DAYS_BEFORE, mailer)

    assert mailer.sent == []


async def test_after_the_trial_the_free_plan_gets_no_reminders(
    database: Database, request: pytest.FixtureRequest, worker_engine: AsyncEngine
) -> None:
    with client_for(database, request, FixedClock(NOW)) as client:
        account_id, _, _ = await landlord_owing_october(database, client)
    mailer = RecordingMailer()

    await run_for(worker_engine, account_id, date(2027, 1, 14), mailer)

    assert mailer.sent == []


async def test_a_failed_send_leaves_no_log_so_the_worker_can_retry(
    database: Database, request: pytest.FixtureRequest, worker_engine: AsyncEngine
) -> None:
    with client_for(database, request, FixedClock(NOW)) as client:
        account_id, _, _ = await landlord_owing_october(database, client)

    with pytest.raises(MailDeliveryError):
        await run_for(worker_engine, account_id, FIVE_DAYS_BEFORE, FailingMailer())

    assert await logged(database, account_id) == []


async def test_one_click_unsubscribe_from_the_header_stops_the_next_reminder(
    database: Database, request: pytest.FixtureRequest, worker_engine: AsyncEngine
) -> None:
    mailer = RecordingMailer()
    with client_for(database, request, FixedClock(NOW)) as client:
        account_id, _, _ = await landlord_owing_october(database, client)
        await run_for(worker_engine, account_id, FIVE_DAYS_BEFORE, mailer)
        message = SmtpMailer(SMTP, FixedClock(NOW)).build(mailer.sent[0])
        one_click = message["List-Unsubscribe"].strip("<>")
        target = urlsplit(one_click)
        response = client.post(
            f"{target.path}?{target.query}",
            content=message["List-Unsubscribe-Post"],
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    await run_for(worker_engine, account_id, date(2026, 11, 18), mailer)

    assert message["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert one_click.startswith(f"{APP_URL}/api/public/unsubscribe?")
    assert response.status_code < 300
    assert len(mailer.sent) == 1


async def test_a_missed_first_reminder_goes_out_on_the_next_day_the_worker_runs(
    database: Database, request: pytest.FixtureRequest, worker_engine: AsyncEngine
) -> None:
    with client_for(database, request, FixedClock(NOW)) as client:
        account_id, _, _ = await landlord_owing_october(database, client)
    mailer = RecordingMailer()

    for today in (date(2026, 11, 15), date(2026, 11, 16), date(2026, 11, 18)):
        await run_for(worker_engine, account_id, today, mailer)

    assert [sent.subject for sent in mailer.sent] == [
        "Tus formularios 1683 de octubre de 2026 vencen el 19/11/2026",
        "Mañana vencen tus formularios 1683 de octubre de 2026",
    ]
