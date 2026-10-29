import csv
import io
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid7

import asyncpg
import pytest
from fastapi.testclient import TestClient

from api_client import FixedClock
from database import Database
from tax_flows import add_renter, client_for, pay, register, save_ruc, send, start_leases

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 27, 15, 0, tzinfo=UTC)
PAYMENTS = "/api/app/exports/payments.csv?year=2026"
DECLARATIONS = "/api/app/exports/declarations.csv?year=2026"


def rows(text: str) -> list[list[str]]:
    assert text.startswith("﻿")
    return list(csv.reader(io.StringIO(text.removeprefix("﻿"))))


def a_year_of_collections(client: TestClient) -> str:
    save_ruc(client)
    ana = add_renter(client, "Ana", {"doc_type": "dni", "number": "45678912"})
    luis = add_renter(client, "Luis")
    ana_lease, garage = start_leases(
        client,
        {"renter_id": ana, "start_date": "2025-06-01", "opening_balance_pre_2026_cents": 120_000},
        {"renter_id": luis, "tax_treatment": "unsupported"},
    )
    body = {
        "id": str(uuid7()),
        "amount_cents": 150_000,
        "received_on": "2026-10-10",
        "method": "transfer",
        "note": "=HYPERLINK(1)",
    }
    assert send(client, "POST", f"/api/app/leases/{ana_lease}/payments", body).status_code == 201
    pay(client, garage, 30_000, "2026-10-12")
    voided = pay(client, garage, 9_000, "2026-10-13")
    send(client, "POST", f"/api/app/payments/{voided}/void", {"reason": "Error"})
    tax_payment = {
        "id": str(uuid7()),
        "period": "2026-10",
        "renter_id": ana,
        "amount_cents": 1_500,
        "paid_on": "2026-10-27",
        "order_number": "1234567890",
    }
    assert send(client, "POST", "/api/app/tax/payments", tax_payment).status_code == 201
    return ana


async def test_the_accountant_gets_the_years_payments_and_declarations(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with client_for(database, request, FixedClock(NOW)) as client:
        register(client)
        ana = a_year_of_collections(client)
        payments = client.get(PAYMENTS)
        declarations = client.get(DECLARATIONS)

    owner = await asyncpg.connect(database.dsn("casero_owner"))
    try:
        exported = await owner.fetch(
            "SELECT action, changed_fields FROM audit_log WHERE action LIKE 'export.%'"
            " AND account_id = (SELECT account_id FROM renters WHERE id = $1) ORDER BY action",
            UUID(ana),
        )
    finally:
        await owner.close()
    assert [(row["action"], row["changed_fields"]) for row in exported] == [
        ("export.declarations", ["year"]),
        ("export.payments", ["year"]),
    ]
    assert payments.headers["content-type"] == "text/csv; charset=utf-8"
    assert payments.headers["content-disposition"] == 'attachment; filename="casero-pagos-2026.csv"'
    assert payments.headers["cache-control"] == "no-store"
    assert rows(payments.text) == [
        [
            "Fecha de cobro",
            "Inquilino",
            "Tipo de documento",
            "Número de documento",
            "Unidad",
            "Medio",
            "Monto",
            "Deuda de 2025 o antes",
            "Monto gravado",
            "Entra al 1683",
            "Nota",
        ],
        [
            "10/10/2026",
            "Ana",
            "DNI",
            "45678912",
            "Cuarto 0 · Casa",
            "Transferencia",
            "1500.00",
            "1200.00",
            "300.00",
            "Sí",
            "'=HYPERLINK(1)",
        ],
        ["12/10/2026", "Luis", "", "", "Cuarto 1 · Casa", "Yape", "300.00", "0.00", "", "No", ""],
    ]
    assert rows(declarations.text) == [
        [
            "Período",
            "Inquilino",
            "Tipo de documento",
            "Número de documento",
            "Base",
            "Tributo",
            "Pagado",
            "Pendiente",
            "Vencimiento",
            "Números de orden",
            "Falta el documento",
        ],
        [
            "2026-10",
            "Ana",
            "DNI",
            "45678912",
            "300.00",
            "15.00",
            "15.00",
            "0.00",
            "19/11/2026",
            "1234567890",
            "No",
        ],
    ]


async def test_another_account_gets_only_the_headers(
    database: Database, request: pytest.FixtureRequest
) -> None:
    clock = FixedClock(NOW)
    with client_for(database, request, clock) as ana, client_for(database, request, clock) as luis:
        register(ana)
        register(luis)
        a_year_of_collections(ana)
        payments = luis.get(PAYMENTS)
        declarations = luis.get(DECLARATIONS)

    assert len(rows(payments.text)) == 1
    assert len(rows(declarations.text)) == 1


async def test_the_free_plan_has_no_accountant_export(
    database: Database, request: pytest.FixtureRequest
) -> None:
    clock = FixedClock(NOW)
    email = f"{uuid7()}@example.com"
    with client_for(database, request, clock) as client:
        register(client, email)
        owner = await asyncpg.connect(database.dsn("casero_owner"))
        try:
            await owner.execute(
                "UPDATE users SET email_verified_at = $1 WHERE email = $2", NOW, email
            )
        finally:
            await owner.close()
        clock.advance(timedelta(days=29))
        client.get("/api/app/account")
        clock.advance(timedelta(days=9))
        responses = [client.get(PAYMENTS), client.get(DECLARATIONS), client.get(PAYMENTS[:-5])]

    assert [(r.status_code, r.json().get("detail")) for r in responses[:2]] == [
        (403, "accountant_export_unavailable"),
        (403, "accountant_export_unavailable"),
    ]
    assert responses[2].status_code == 422
