from datetime import UTC, datetime
from uuid import uuid7

import pytest
from fastapi.testclient import TestClient

from api_client import FixedClock
from database import Database
from tax_flows import add_renter, client_for, pay, register, save_ruc, send, start_leases

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 27, 15, 0, tzinfo=UTC)
OLD_DEBT = {"start_date": "2025-06-01", "opening_balance_pre_2026_cents": 50_000}


def ana(client: TestClient) -> str:
    register(client)
    save_ruc(client)
    return add_renter(client, "Ana", {"doc_type": "dni", "number": "45678912"})


def pay_sunat_for_october(client: TestClient, renter_id: str, base_cents: int) -> str:
    body = {
        "id": str(uuid7()),
        "period": "2026-10",
        "renter_id": renter_id,
        "amount_cents": 4_000,
        "paid_on": "2026-10-27",
        "order_number": "1234567890",
        "declared_base_cents": base_cents,
    }
    assert send(client, "POST", "/api/app/tax/payments", body).status_code == 201
    return str(body["id"])


def void(client: TestClient, kind: str, item_id: str) -> list[str]:
    response = send(client, "POST", f"/api/app/{kind}/{item_id}/void", {"reason": "Error"})
    assert response.status_code == 200
    paid_to_sunat: list[str] = response.json()["paid_to_sunat"]
    return paid_to_sunat


async def test_a_payment_void_names_the_months_paid_to_sunat_it_changed(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with client_for(database, request, FixedClock(NOW)) as client:
        renter_id = ana(client)
        room, garage = start_leases(
            client,
            {"renter_id": renter_id, "control_from_period": "2026-09", **OLD_DEBT},
            {"renter_id": renter_id, "tax_treatment": "unsupported"},
        )
        old_debt_paid = pay(client, room, 50_000, "2026-09-05")
        october = pay(client, room, 80_000, "2026-10-05")
        untaxed = pay(client, garage, 30_000, "2026-10-06")
        sunat = pay_sunat_for_october(client, renter_id, 80_000)

        outside_the_tax = void(client, "payments", untaxed)
        moved_the_old_debt = void(client, "payments", old_debt_paid)
        again = void(client, "payments", old_debt_paid)
        send(client, "POST", f"/api/app/tax/payments/{sunat}/void", {"reason": "Error"})
        after_voiding_sunat = void(client, "payments", october)

    assert outside_the_tax == []
    assert moved_the_old_debt == again == ["2026-10"]
    assert after_voiding_sunat == []


async def test_a_charge_void_names_the_months_paid_to_sunat_it_changed(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with client_for(database, request, FixedClock(NOW)) as client:
        renter_id = ana(client)
        [lease] = start_leases(client, {"renter_id": renter_id, **OLD_DEBT})
        pay(client, lease, 130_000, "2026-10-05")
        pay_sunat_for_october(client, renter_id, 80_000)
        charges = client.get(f"/api/app/leases/{lease}/statement").json()["charges"]
        ids = {charge["kind"]: charge["id"] for charge in charges}

        rent = void(client, "charges", ids["rent"])
        old_debt = void(client, "charges", ids["opening_balance"])

    assert rent == []
    assert old_debt == ["2026-10"]
