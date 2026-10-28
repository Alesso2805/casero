from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4, uuid7

import pytest
from fastapi.testclient import TestClient

from api_client import FixedClock, address_for, api_client
from database import Database

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 27, 15, 0, tzinfo=UTC)
CSRF = "__Host-casero_csrf"


@dataclass(frozen=True)
class Lease:
    id: str
    client: TestClient


def send(client: TestClient, method: str, path: str, body: object = None) -> Any:
    return client.request(method, path, json=body, headers={"X-CSRF-Token": client.cookies[CSRF]})


def start_lease(client: TestClient, **overrides: object) -> str:
    client.get("/api/public/csrf")
    registered = send(
        client,
        "POST",
        "/api/public/registration",
        {
            "email": f"{uuid7()}@example.com",
            "password": "una clave bien larga",
            "display_name": "Casera",
            "accept_terms_and_privacy": True,
            "consent_sensitive_data": True,
        },
    )
    assert registered.status_code == 201
    house = send(
        client,
        "POST",
        "/api/app/properties",
        {"name": "Casa", "ownership": "sole", "units": [{"name": "Cuarto", "kind": "room"}]},
    ).json()
    renter = send(client, "POST", "/api/app/renters", {"full_name": "Ana"}).json()
    lease = {
        "id": str(uuid7()),
        "unit_id": house["units"][0]["id"],
        "renter_id": renter["id"],
        "monthly_rent_cents": 80_000,
        "due_day": 5,
        "start_date": "2026-03-01",
        "control_from_period": "2026-09",
        "tax_treatment": "standard",
        **overrides,
    }
    assert send(client, "POST", "/api/app/leases", lease).status_code == 201
    return str(lease["id"])


def pay(client: TestClient, lease_id: str, **overrides: object) -> Any:
    body = {
        "id": str(uuid7()),
        "amount_cents": 50_000,
        "received_on": "2026-10-10",
        "method": "yape",
        **overrides,
    }
    return send(client, "POST", f"/api/app/leases/{lease_id}/payments", body)


def client_for(database: Database, request: pytest.FixtureRequest) -> Any:
    return api_client(
        database, address_for(request.node.name), FixedClock(NOW), registration_mode="open"
    )


async def test_payments_cover_the_oldest_charges_and_leave_a_credit(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with client_for(database, request) as client:
        lease_id = start_lease(client)
        partial = pay(client, lease_id)
        after_partial = client.get(f"/api/app/leases/{lease_id}/statement").json()
        pay(client, lease_id, amount_cents=200_000, received_on="2026-10-20", method="transfer")
        after_all = client.get(f"/api/app/leases/{lease_id}/statement").json()

    assert partial.status_code == 201
    assert partial.json()["bank_threshold_cents"] is None
    assert [
        (c["period"], c["outstanding_cents"], c["status"], c["partial"])
        for c in after_partial["charges"]
    ] == [("2026-09", 30_000, "overdue", True), ("2026-10", 80_000, "overdue", False)]
    assert (after_partial["balance_cents"], after_partial["up_to_date"]) == (110_000, False)
    assert [c["status"] for c in after_all["charges"]] == ["paid", "paid"]
    assert (after_all["balance_cents"], after_all["credit_cents"]) == (-90_000, 90_000)
    assert after_all["up_to_date"] is True
    assert [p["amount_cents"] for p in after_all["payments"]] == [50_000, 200_000]


async def test_sending_the_same_payment_again_records_it_once(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with client_for(database, request) as ana, client_for(database, request) as luis:
        lease_id = start_lease(ana)
        other_lease = start_lease(luis)
        body = {"id": str(uuid7())}
        first = pay(ana, lease_id, **body)
        again = pay(ana, lease_id, **body)
        changed = pay(ana, lease_id, **body, amount_cents=60_000)
        elsewhere = pay(luis, other_lease, **body)
        payments = ana.get(f"/api/app/leases/{lease_id}/statement").json()["payments"]

    assert (first.status_code, again.status_code) == (201, 200)
    assert again.json() == first.json()
    assert (changed.status_code, changed.json()["detail"]) == (409, "Conflict")
    assert elsewhere.status_code == 409
    assert len(payments) == 1


@pytest.mark.parametrize(
    ("overrides", "detail"),
    [
        ({"received_on": "2026-10-28"}, "received_in_future"),
        ({"received_on": "2026-08-31"}, "received_before_control"),
        ({"id": str(uuid4())}, None),
        ({"amount_cents": 0}, None),
        ({"method": "guarantee"}, None),
    ],
)
async def test_invalid_payments_are_refused(
    database: Database,
    request: pytest.FixtureRequest,
    overrides: dict[str, object],
    detail: str | None,
) -> None:
    with client_for(database, request) as client:
        lease_id = start_lease(client)
        response = pay(client, lease_id, **overrides)

    assert response.status_code == 422
    if detail is not None:
        assert response.json()["detail"] == detail


async def test_prior_debt_lets_the_landlord_date_receipts_from_2026(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with client_for(database, request) as client:
        lease_id = start_lease(client, opening_balance_2026_cents=40_000)
        response = pay(client, lease_id, received_on="2026-01-15")
        before_2026 = pay(client, lease_id, received_on="2025-12-31")

    assert response.status_code == 201
    assert before_2026.json()["detail"] == "received_before_control"


@pytest.mark.parametrize(
    ("rent", "method", "threshold"),
    [(250_000, "cash", 200_000), (250_000, "transfer", None), (80_000, "cash", None)],
)
async def test_cash_for_a_rent_at_the_threshold_warns_about_banking(
    database: Database,
    request: pytest.FixtureRequest,
    rent: int,
    method: str,
    threshold: int | None,
) -> None:
    with client_for(database, request) as client:
        lease_id = start_lease(client, monthly_rent_cents=rent)
        response = pay(client, lease_id, method=method)

    assert response.json()["bank_threshold_cents"] == threshold


async def test_a_voided_payment_stops_counting_and_voiding_again_changes_nothing(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with client_for(database, request) as ana, client_for(database, request) as luis:
        lease_id = start_lease(ana)
        start_lease(luis)
        payment_id = pay(ana, lease_id).json()["id"]
        void = {"reason": "Lo registré dos veces"}
        voided = send(ana, "POST", f"/api/app/payments/{payment_id}/void", void)
        again = send(ana, "POST", f"/api/app/payments/{payment_id}/void", void)
        intrusion = send(luis, "POST", f"/api/app/payments/{payment_id}/void", void)
        statement = ana.get(f"/api/app/leases/{lease_id}/statement").json()

    assert voided.json()["voided"] is True
    assert again.status_code == 200
    assert intrusion.status_code == 404
    assert statement["balance_cents"] == 160_000
    assert statement["payments"][0]["voided"] is True


async def test_another_account_cannot_see_or_pay_a_lease(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with client_for(database, request) as ana, client_for(database, request) as luis:
        lease_id = start_lease(ana)
        start_lease(luis)
        payment = pay(luis, lease_id)
        statement = luis.get(f"/api/app/leases/{lease_id}/statement")

    assert (payment.status_code, payment.json()["detail"]) == (404, "lease_not_found")
    assert statement.status_code == 404


async def test_writes_need_the_csrf_token(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with client_for(database, request) as client:
        lease_id = start_lease(client)
        response = client.post(
            f"/api/app/leases/{lease_id}/payments",
            json={
                "id": str(uuid7()),
                "amount_cents": 1,
                "received_on": "2026-10-10",
                "method": "cash",
            },
        )

    assert (response.status_code, response.json()["detail"]) == (403, "csrf")
