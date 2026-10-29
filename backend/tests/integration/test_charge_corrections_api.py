from datetime import UTC, datetime
from typing import Any
from uuid import uuid7

import asyncpg
import pytest
from fastapi.testclient import TestClient

from api_client import FixedClock, address_for, api_client
from database import Database

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 27, 15, 0, tzinfo=UTC)
CSRF = "__Host-casero_csrf"
WRONG_AMOUNT = {"reason": "El monto estaba mal"}


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


def charges_by_period(client: TestClient, lease_id: str) -> dict[str | None, Any]:
    statement = client.get(f"/api/app/leases/{lease_id}/statement").json()
    return {charge["period"]: charge for charge in statement["charges"]}


def correct(client: TestClient, lease_id: str, **body: object) -> Any:
    return send(client, "POST", f"/api/app/leases/{lease_id}/charges/corrections", body)


async def owner_execute(database: Database, query: str, *args: object) -> None:
    connection = await asyncpg.connect(database.dsn("casero_owner"))
    try:
        await connection.execute(query, *args)
    finally:
        await connection.close()


def client_for(database: Database, request: pytest.FixtureRequest) -> Any:
    return api_client(
        database, address_for(request.node.name), FixedClock(NOW), registration_mode="open"
    )


async def test_a_voided_rent_is_replaced_by_its_correction(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with client_for(database, request) as client:
        lease_id = start_lease(client)
        october = charges_by_period(client, lease_id)["2026-10"]
        voided = send(client, "POST", f"/api/app/charges/{october['id']}/void", WRONG_AMOUNT)
        body = {"id": str(uuid7()), "corrects_charge_id": october["id"], "amount_cents": 70_000}
        corrected = correct(client, lease_id, **body)
        again = correct(client, lease_id, **body)
        changed = correct(client, lease_id, **{**body, "amount_cents": 60_000})
        statement = client.get(f"/api/app/leases/{lease_id}/statement").json()

    assert voided.json()["voided"] is True
    assert corrected.status_code == 201
    assert {key: corrected.json()[key] for key in ("kind", "period", "due_date")} == {
        "kind": "rent_correction",
        "period": "2026-10",
        "due_date": october["due_date"],
    }
    assert (again.status_code, again.json()) == (200, corrected.json())
    assert (changed.status_code, changed.json()["detail"]) == (409, "Conflict")
    assert [(c["kind"], c["period"], c["voided"]) for c in statement["charges"]] == [
        ("rent", "2026-09", False),
        ("rent", "2026-10", True),
        ("rent_correction", "2026-10", False),
    ]
    assert statement["balance_cents"] == 150_000
    assert statement["charges"][2]["corrects_charge_id"] == october["id"]


async def test_only_a_voided_rent_is_corrected_and_only_once(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with client_for(database, request) as client:
        lease_id = start_lease(client)
        charges = charges_by_period(client, lease_id)
        september, october = charges["2026-09"]["id"], charges["2026-10"]["id"]
        not_voided = correct(
            client, lease_id, id=str(uuid7()), corrects_charge_id=september, amount_cents=1
        )
        send(client, "POST", f"/api/app/charges/{october}/void", WRONG_AMOUNT)
        correct(client, lease_id, id=str(uuid7()), corrects_charge_id=october, amount_cents=1)
        twice = correct(
            client, lease_id, id=str(uuid7()), corrects_charge_id=october, amount_cents=2
        )

    assert (not_voided.status_code, not_voided.json()["detail"]) == (422, "not_a_voided_rent")
    assert (twice.status_code, twice.json()["detail"]) == (422, "already_corrected")


async def test_voiding_is_idempotent_and_stays_in_the_account(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with client_for(database, request) as ana, client_for(database, request) as luis:
        lease_id = start_lease(ana)
        start_lease(luis)
        rent = charges_by_period(ana, lease_id)["2026-09"]["id"]
        first = send(ana, "POST", f"/api/app/charges/{rent}/void", WRONG_AMOUNT)
        again = send(ana, "POST", f"/api/app/charges/{rent}/void", WRONG_AMOUNT)
        intrusion = send(luis, "POST", f"/api/app/charges/{rent}/void", WRONG_AMOUNT)
        foreign = correct(luis, lease_id, id=str(uuid7()), corrects_charge_id=rent, amount_cents=1)

    assert (again.status_code, again.json()) == (200, first.json())
    assert (intrusion.status_code, intrusion.json()["detail"]) == (404, "charge_not_found")
    assert (foreign.status_code, foreign.json()["detail"]) == (404, "lease_not_found")


def prior_debt(client: TestClient, lease_id: str, **body: object) -> Any:
    return send(client, "POST", f"/api/app/leases/{lease_id}/charges/prior-debts", body)


async def test_a_wrong_prior_debt_is_voided_and_entered_again_once_per_era(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with client_for(database, request) as client:
        lease_id = start_lease(client, opening_balance_2026_cents=40_000)
        wrong = charges_by_period(client, lease_id)[None]["id"]
        while_valid = prior_debt(
            client, lease_id, id=str(uuid7()), pre_2026=False, amount_cents=35_000
        )
        send(client, "POST", f"/api/app/charges/{wrong}/void", WRONG_AMOUNT)
        body = {"id": str(uuid7()), "pre_2026": False, "amount_cents": 35_000}
        right = prior_debt(client, lease_id, **body)
        again = prior_debt(client, lease_id, **body)
        from_2025 = prior_debt(client, lease_id, id=str(uuid7()), pre_2026=True, amount_cents=1)
        statement = client.get(f"/api/app/leases/{lease_id}/statement").json()

    assert (while_valid.status_code, while_valid.json()["detail"]) == (422, "prior_debt_exists")
    assert right.status_code == 201
    assert (right.json()["kind"], right.json()["due_date"]) == ("opening_balance", "2026-08-31")
    assert (again.status_code, again.json()) == (200, right.json())
    assert (from_2025.status_code, from_2025.json()["detail"]) == (
        422,
        "balance_pre_2026_without_months",
    )
    assert statement["balance_cents"] == 160_000 + 35_000


def change_rent(client: TestClient, lease_id: str, **body: object) -> Any:
    return send(client, "POST", f"/api/app/leases/{lease_id}/rent-changes", body)


async def test_a_new_rent_starts_with_the_next_period_not_yet_charged(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with client_for(database, request) as client, client_for(database, request) as later:
        lease_id = start_lease(client)
        future_lease = start_lease(later, start_date="2026-12-01", control_from_period="2026-12")
        body = {"id": str(uuid7()), "monthly_rent_cents": 90_000}
        changed = change_rent(client, lease_id, **body)
        again = change_rent(client, lease_id, **body)
        other = change_rent(client, lease_id, **{**body, "monthly_rent_cents": 95_000})
        not_started = change_rent(later, future_lease, id=str(uuid7()), monthly_rent_cents=70_000)
        statement = client.get(f"/api/app/leases/{lease_id}/statement").json()

    assert (changed.status_code, changed.json()["effective_period"]) == (201, "2026-11")
    assert (again.status_code, again.json()) == (200, changed.json())
    assert other.status_code == 409
    assert not_started.json()["effective_period"] == "2026-12"
    assert [c["amount_cents"] for c in statement["charges"]] == [80_000, 80_000]


async def test_an_ended_lease_keeps_its_rent(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with client_for(database, request) as client:
        lease_id = start_lease(client)
        await owner_execute(
            database, "UPDATE leases SET ended_at = '2026-10-15' WHERE id = $1::uuid", lease_id
        )
        refused = change_rent(client, lease_id, id=str(uuid7()), monthly_rent_cents=90_000)

    assert (refused.status_code, refused.json()["detail"]) == (422, "lease_ended")


def adjust(client: TestClient, lease_id: str, **body: object) -> Any:
    return send(client, "POST", f"/api/app/leases/{lease_id}/charges/adjustments", body)


async def test_debits_and_credits_by_hand_change_the_balance_from_today(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with client_for(database, request) as client:
        lease_id = start_lease(client)
        debit = {"id": str(uuid7()), "amount_cents": 5_000}
        charged = adjust(client, lease_id, **debit)
        again = adjust(client, lease_id, **debit)
        changed = adjust(client, lease_id, **{**debit, "amount_cents": 6_000})
        credited = adjust(client, lease_id, id=str(uuid7()), amount_cents=-20_000)
        statement = client.get(f"/api/app/leases/{lease_id}/statement").json()

    assert charged.status_code == 201
    assert (charged.json()["kind"], charged.json()["due_date"]) == ("adjustment", "2026-10-27")
    assert (again.status_code, again.json()) == (200, charged.json())
    assert changed.status_code == 409
    assert credited.json()["amount_cents"] == -20_000
    assert statement["balance_cents"] == 160_000 + 5_000 - 20_000
    [credit_line] = [c for c in statement["charges"] if c["amount_cents"] < 0]
    assert credit_line["status"] is None


async def test_a_zero_adjustment_or_another_accounts_lease_is_refused(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with client_for(database, request) as ana, client_for(database, request) as luis:
        lease_id = start_lease(ana)
        start_lease(luis)
        zero = adjust(ana, lease_id, id=str(uuid7()), amount_cents=0)
        foreign = adjust(luis, lease_id, id=str(uuid7()), amount_cents=1_000)

    assert zero.status_code == 422
    assert (foreign.status_code, foreign.json()["detail"]) == (404, "lease_not_found")
