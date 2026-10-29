from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid7

import asyncpg
import pytest
from fastapi.testclient import TestClient

from api_client import FixedClock
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
