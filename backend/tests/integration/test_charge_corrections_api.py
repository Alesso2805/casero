from datetime import UTC, datetime
from typing import Any
from uuid import uuid7

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


async def test_voiding_is_idempotent_spares_prior_debt_and_stays_in_the_account(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with client_for(database, request) as ana, client_for(database, request) as luis:
        lease_id = start_lease(ana, opening_balance_2026_cents=40_000)
        start_lease(luis)
        charges = charges_by_period(ana, lease_id)
        rent, prior = charges["2026-09"]["id"], charges[None]["id"]
        first = send(ana, "POST", f"/api/app/charges/{rent}/void", WRONG_AMOUNT)
        again = send(ana, "POST", f"/api/app/charges/{rent}/void", WRONG_AMOUNT)
        prior_debt = send(ana, "POST", f"/api/app/charges/{prior}/void", WRONG_AMOUNT)
        intrusion = send(luis, "POST", f"/api/app/charges/{rent}/void", WRONG_AMOUNT)
        foreign = correct(luis, lease_id, id=str(uuid7()), corrects_charge_id=rent, amount_cents=1)

    assert (again.status_code, again.json()) == (200, first.json())
    assert (prior_debt.status_code, prior_debt.json()["detail"]) == (422, "charge_not_voidable")
    assert (intrusion.status_code, intrusion.json()["detail"]) == (404, "charge_not_found")
    assert (foreign.status_code, foreign.json()["detail"]) == (404, "lease_not_found")
