import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid7

import asyncpg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncConnection

from api_client import FixedClock
from casero.accounts.application.context import AccountContext
from casero.accounts.application.entitlements import GetEntitlements
from casero.accounts.infrastructure.account import SqlPlans, SqlProfiles, SqlSubscriptions
from casero.leases.infrastructure.leases import SqlLeaseStore
from casero.leases.infrastructure.renters import SqlRenterHolders
from casero.ledger.infrastructure.ledger import SqlLedger
from casero.properties.infrastructure.properties import SqlPropertyStore
from casero.shared.infrastructure.audit import SqlAuditLog
from casero.shared.infrastructure.database import create_engine, set_account_context
from casero.shared.kernel.periods import Period
from casero.tax.application.declarations import GetDeclarations
from casero.tax.application.payments import RecordedTaxPayment, RecordTaxPayment
from casero.tax.application.sunat_payments import NewTaxPayment
from casero.tax.infrastructure.payments import SqlTaxPayments
from casero.tax.infrastructure.rule_book import SqlTaxRuleBook
from database import Database
from tax_flows import add_renter, client_for, pay, register, save_ruc, send, start_leases

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 27, 15, 0, tzinfo=UTC)
ANA_DNI = {"doc_type": "dni", "number": "45678912"}
PAYMENTS = "/api/app/tax/payments"


def ana_paid_in_october(client: TestClient) -> str:
    register(client)
    save_ruc(client)
    ana = add_renter(client, "Ana", ANA_DNI)
    [lease] = start_leases(client, {"renter_id": ana})
    pay(client, lease, 80_000, "2026-10-05")
    return ana


def tax_payment(renter_id: str, **overrides: object) -> dict[str, object]:
    return {
        "id": str(uuid7()),
        "period": "2026-10",
        "renter_id": renter_id,
        "amount_cents": 4_000,
        "paid_on": "2026-10-27",
        "order_number": "1234567890",
        **overrides,
    }


async def owner_rows(database: Database, query: str, *args: object) -> list[asyncpg.Record]:
    owner = await asyncpg.connect(database.dsn("casero_owner"))
    try:
        return await owner.fetch(query, *args)
    finally:
        await owner.close()


async def test_a_payment_keeps_the_declarations_document_and_base_and_replays(
    database: Database, request: pytest.FixtureRequest
) -> None:
    clock = FixedClock(NOW)
    with client_for(database, request, clock) as ana, client_for(database, request, clock) as luis:
        renter_id = ana_paid_in_october(ana)
        luis_renter = ana_paid_in_october(luis)
        body = tax_payment(renter_id)
        first = send(ana, "POST", PAYMENTS, body)
        again = send(ana, "POST", PAYMENTS, body)
        changed = send(ana, "POST", PAYMENTS, {**body, "amount_cents": 3_000})
        elsewhere = send(luis, "POST", PAYMENTS, {**body, "renter_id": luis_renter})

    assert first.status_code == 201
    assert first.json() == {
        "id": body["id"],
        "period": "2026-10",
        "renter_id": renter_id,
        "amount_cents": 4_000,
        "paid_on": "2026-10-27",
        "order_number": "1234567890",
        "base_cents": 80_000,
        "voided": False,
    }
    assert (again.status_code, again.json()) == (200, first.json())
    assert (changed.status_code, changed.json()["detail"]) == (409, "Conflict")
    assert (elsewhere.status_code, elsewhere.json()["detail"]) == (409, "Conflict")
    [stored] = await owner_rows(
        database,
        "SELECT p.renter_doc_hmac = r.doc_hmac AS same_document, p.base_cents,"
        " (SELECT count(*) FROM audit_log a WHERE a.entity_id = p.id) AS audited"
        " FROM tax_payments p JOIN renters r ON r.id = p.renter_id WHERE p.id = $1",
        UUID(str(body["id"])),
    )
    assert (stored["same_document"], stored["base_cents"], stored["audited"]) == (True, 80_000, 1)


@pytest.mark.parametrize(
    ("overrides", "status", "detail"),
    [
        ({"paid_on": "2026-09-30"}, 422, "paid_before_period"),
        ({"paid_on": "2026-10-28"}, 422, "paid_in_future"),
        ({"period": "2026-09"}, 404, "declaration_not_found"),
        ({"period": "2027-01"}, 422, "unknown_year"),
        ({"order_number": "12-34"}, 422, None),
        ({"amount_cents": 0}, 422, None),
        ({"id": str(UUID(int=1))}, 422, None),
    ],
)
async def test_a_payment_needs_a_declaration_and_sensible_data(
    database: Database,
    request: pytest.FixtureRequest,
    overrides: dict[str, object],
    status: int,
    detail: str | None,
) -> None:
    with client_for(database, request, FixedClock(NOW)) as client:
        renter_id = ana_paid_in_october(client)
        response = send(client, "POST", PAYMENTS, tax_payment(renter_id, **overrides))

    assert response.status_code == status
    if detail:
        assert response.json()["detail"] == detail


async def test_a_declaration_without_the_tenants_document_takes_no_payment(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with client_for(database, request, FixedClock(NOW)) as client:
        register(client)
        rosa = add_renter(client, "Rosa")
        [lease] = start_leases(client, {"renter_id": rosa})
        pay(client, lease, 80_000, "2026-10-05")
        response = send(client, "POST", PAYMENTS, tax_payment(rosa))

    assert (response.status_code, response.json()["detail"]) == (422, "declaration_incomplete")


async def test_voiding_twice_returns_the_voided_payment_and_audits_it_once(
    database: Database, request: pytest.FixtureRequest
) -> None:
    clock = FixedClock(NOW)
    with client_for(database, request, clock) as ana, client_for(database, request, clock) as luis:
        renter_id = ana_paid_in_october(ana)
        register(luis)
        payment_id = send(ana, "POST", PAYMENTS, tax_payment(renter_id)).json()["id"]
        from_luis = send(luis, "POST", f"{PAYMENTS}/{payment_id}/void", {"reason": "Error"})
        voided = send(ana, "POST", f"{PAYMENTS}/{payment_id}/void", {"reason": "Error"})
        again = send(ana, "POST", f"{PAYMENTS}/{payment_id}/void", {"reason": "Otra vez"})
        unknown = send(ana, "POST", f"{PAYMENTS}/{uuid7()}/void", {"reason": "Error"})

    assert (from_luis.status_code, from_luis.json()["detail"]) == (404, "tax_payment_not_found")
    assert (voided.status_code, voided.json()["voided"]) == (200, True)
    assert (again.status_code, again.json()) == (200, voided.json())
    assert unknown.status_code == 404
    rows = await owner_rows(
        database,
        "SELECT action FROM audit_log WHERE entity_id = $1 ORDER BY at, id",
        UUID(payment_id),
    )
    assert [row["action"] for row in rows] == ["tax_payment.created", "tax_payment.voided"]


async def test_the_free_plan_cannot_record_or_void_sunat_payments(
    database: Database, request: pytest.FixtureRequest
) -> None:
    clock = FixedClock(NOW)
    with client_for(database, request, clock) as client:
        renter_id = ana_paid_in_october(client)
        payment_id = send(client, "POST", PAYMENTS, tax_payment(renter_id)).json()["id"]
        await owner_rows(
            database,
            "UPDATE users SET email_verified_at = $1"
            " WHERE id = (SELECT created_by FROM tax_payments WHERE id = $2)",
            NOW,
            UUID(payment_id),
        )
        clock.advance(timedelta(days=29))
        client.get("/api/app/account")
        clock.advance(timedelta(days=9))
        record = send(client, "POST", PAYMENTS, tax_payment(renter_id, paid_on="2026-10-27"))
        void = send(client, "POST", f"{PAYMENTS}/{payment_id}/void", {"reason": "Error"})

    responses: list[Any] = [record, void]
    assert [(r.status_code, r.json()["detail"]) for r in responses] == [
        (403, "tax_module_unavailable"),
        (403, "tax_module_unavailable"),
    ]


def october_card(client: TestClient, renter_id: str) -> Any:
    month = client.get("/api/app/tax/declarations?period=2026-10").json()
    return next(card for card in month["declarations"] if card["renter_id"] == renter_id)


async def test_the_card_follows_what_was_paid_and_what_changed_after(
    database: Database, request: pytest.FixtureRequest
) -> None:
    clock = FixedClock(NOW)
    with client_for(database, request, clock) as client:
        register(client)
        save_ruc(client)
        ana = add_renter(client, "Ana", ANA_DNI)
        [lease] = start_leases(client, {"renter_id": ana})
        first = pay(client, lease, 80_000, "2026-10-05")
        before = october_card(client, ana)
        payment = send(client, "POST", PAYMENTS, tax_payment(ana))
        declared = october_card(client, ana)
        clock.advance(timedelta(minutes=5))
        second = pay(client, lease, 20_000, "2026-10-20")
        went_up = october_card(client, ana)
        for payment_id in (first, second):
            send(client, "POST", f"/api/app/payments/{payment_id}/void", {"reason": "Error"})
        went_down = october_card(client, ana)

    assert (before["paid_cents"], before["pending_cents"], before["after_declaring"]) == (
        0,
        4_000,
        None,
    )
    assert declared["payments"] == [
        {
            "id": payment.json()["id"],
            "amount_cents": 4_000,
            "paid_on": "2026-10-27",
            "order_number": "1234567890",
        }
    ]
    assert (declared["paid_cents"], declared["pending_cents"], declared["after_declaring"]) == (
        4_000,
        0,
        None,
    )
    assert (went_up["base_cents"], went_up["pending_cents"]) == (100_000, 1_000)
    assert went_up["after_declaring"] == {
        "kind": "up",
        "base_difference_cents": 20_000,
        "tax_difference_cents": 1_000,
    }
    assert (went_down["collected_cents"], went_down["paid_cents"]) == (0, 4_000)
    assert went_down["after_declaring"] == {
        "kind": "down",
        "base_difference_cents": 80_000,
        "tax_difference_cents": 0,
    }


async def test_a_base_that_rose_without_new_money_says_so(
    database: Database, request: pytest.FixtureRequest
) -> None:
    clock = FixedClock(NOW)
    with client_for(database, request, clock) as client:
        register(client)
        save_ruc(client)
        ana = add_renter(client, "Ana", ANA_DNI)
        old_debt_of_500 = {"start_date": "2025-06-01", "opening_balance_pre_2026_cents": 50_000}
        [lease] = start_leases(client, {"renter_id": ana, **old_debt_of_500})
        pay(client, lease, 130_000, "2026-10-05")
        send(client, "POST", PAYMENTS, tax_payment(ana))
        clock.advance(timedelta(minutes=5))
        charges = client.get(f"/api/app/leases/{lease}/statement").json()["charges"]
        [old_debt] = [c["id"] for c in charges if c["kind"] == "opening_balance"]
        send(client, "POST", f"/api/app/charges/{old_debt}/void", {"reason": "Ya me la pagó"})
        card = october_card(client, ana)

    assert card["base_cents"] == 130_000
    assert card["after_declaring"] == {
        "kind": "base_up",
        "base_difference_cents": 50_000,
        "tax_difference_cents": 2_500,
    }


async def test_a_new_document_after_paying_and_an_overdue_month_without_payment(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with client_for(database, request, FixedClock(NOW)) as client:
        register(client)
        save_ruc(client)
        ana = add_renter(client, "Ana", ANA_DNI)
        [lease] = start_leases(client, {"renter_id": ana, "control_from_period": "2026-09"})
        pay(client, lease, 80_000, "2026-09-10")
        pay(client, lease, 80_000, "2026-10-05")
        send(client, "POST", PAYMENTS, tax_payment(ana))
        send(
            client,
            "PUT",
            f"/api/app/renters/{ana}",
            {"full_name": "Ana", "document": {"doc_type": "ce", "number": "001234567"}},
        )
        october = october_card(client, ana)
        september = client.get("/api/app/tax/declarations?period=2026-09").json()

    assert october["doc_number"] == "001234567"
    assert (october["paid_cents"], october["pending_cents"]) == (4_000, 0)
    assert [p["amount_cents"] for p in october["payments"]] == [4_000]
    assert october["after_declaring"]["kind"] == "document_changed"
    assert september["due_on"] == "2026-10-21"
    assert september["declarations"][0]["after_declaring"] == {
        "kind": "overdue_unpaid",
        "base_difference_cents": 0,
        "tax_difference_cents": 0,
    }


@asynccontextmanager
async def two_transactions(
    database: Database, account_id: UUID
) -> AsyncIterator[tuple[AsyncConnection, AsyncConnection]]:
    engine = create_engine(
        database.dsn("casero_app").replace("postgresql://", "postgresql+asyncpg://", 1)
    )
    try:
        async with engine.connect() as first, engine.connect() as second:
            for connection in (first, second):
                await connection.begin()
                await set_account_context(connection, account_id)
            yield first, second
    finally:
        await engine.dispose()


def record_with(connection: AsyncConnection) -> RecordTaxPayment:
    clock = FixedClock(NOW)
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
    return RecordTaxPayment(
        SqlProfiles(connection),
        declarations,
        SqlTaxPayments(connection),
        SqlAuditLog(connection),
        clock,
    )


async def test_the_same_sunat_payment_sent_twice_at_once_is_replayed_not_refused(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with client_for(database, request, FixedClock(NOW)) as client:
        renter_id = ana_paid_in_october(client)
    [row] = await owner_rows(
        database,
        "SELECT account_id, user_id FROM account_members m JOIN renters r"
        " USING (account_id) WHERE r.id = $1",
        UUID(renter_id),
    )
    context = AccountContext(row["account_id"], row["user_id"])
    new = NewTaxPayment(
        uuid7(), Period(2026, 10), UUID(renter_id), 4_000, date(2026, 10, 27), "1234567890"
    )

    async with two_transactions(database, context.account_id) as (first, second):
        recorded = await record_with(first)(context, new)
        resent = asyncio.create_task(record_with(second)(context, new))
        await asyncio.sleep(0.3)
        waited_for_the_account = not resent.done()
        await first.commit()
        replayed = await resent
        await second.commit()

    assert isinstance(recorded, RecordedTaxPayment)
    assert not recorded.replayed
    assert waited_for_the_account
    assert isinstance(replayed, RecordedTaxPayment)
    assert replayed.replayed
