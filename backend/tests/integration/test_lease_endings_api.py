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
        "end_date": "2026-11-10",
        "tax_treatment": "standard",
        **overrides,
    }
    assert send(client, "POST", "/api/app/leases", lease).status_code == 201
    return str(lease["id"])


def end_date(client: TestClient, lease_id: str, value: str | None) -> Any:
    return send(client, "POST", f"/api/app/leases/{lease_id}/end-date", {"end_date": value})


def terminate(client: TestClient, lease_id: str, **body: object) -> Any:
    return send(client, "POST", f"/api/app/leases/{lease_id}/termination", body)


def client_for(database: Database, request: pytest.FixtureRequest) -> Any:
    return api_client(
        database, address_for(request.node.name), FixedClock(NOW), registration_mode="open"
    )


async def test_the_planned_end_is_extended_or_removed_but_never_set_in_the_past(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with client_for(database, request) as client:
        lease_id = start_lease(client)
        extended = end_date(client, lease_id, "2027-11-10")
        removed = end_date(client, lease_id, None)
        past = end_date(client, lease_id, "2026-10-26")

    assert (extended.status_code, extended.json()["end_date"]) == (200, "2027-11-10")
    assert extended.json()["ending_soon"] is False
    assert removed.json()["end_date"] is None
    assert (past.status_code, past.json()["detail"]) == (422, "end_in_past")


async def test_ending_voids_the_rents_after_it_and_records_the_credit_once(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with client_for(database, request) as client:
        lease_id = start_lease(client)
        body = {"ended_on": "2026-09-20", "credit": {"id": str(uuid7()), "amount_cents": 10_000}}
        ended = terminate(client, lease_id, **body)
        again = terminate(client, lease_id, **body)
        other_day = terminate(client, lease_id, ended_on="2026-09-25")
        renewal = end_date(client, lease_id, "2027-01-01")
        statement = client.get(f"/api/app/leases/{lease_id}/statement").json()

    assert (ended.status_code, ended.json()["ended_at"]) == (200, "2026-09-20")
    assert (again.status_code, again.json()) == (200, ended.json())
    assert (other_day.status_code, other_day.json()["detail"]) == (422, "lease_ended")
    assert (renewal.status_code, renewal.json()["detail"]) == (422, "lease_ended")
    assert [(c["kind"], c["period"], c["voided"]) for c in statement["charges"]] == [
        ("rent", "2026-09", False),
        ("rent", "2026-10", True),
        ("adjustment", None, False),
    ]
    assert statement["balance_cents"] == 80_000 - 10_000


@pytest.mark.parametrize(
    ("ended_on", "detail"),
    [("2026-10-28", "end_in_future"), ("2026-08-31", "end_before_control")],
)
async def test_an_end_after_today_or_before_the_control_month_is_refused(
    database: Database, request: pytest.FixtureRequest, ended_on: str, detail: str
) -> None:
    with client_for(database, request) as client:
        lease_id = start_lease(client)
        response = terminate(client, lease_id, ended_on=ended_on)

    assert (response.status_code, response.json()["detail"]) == (422, detail)


@pytest.mark.parametrize(
    ("start", "rents"),
    [("2026-12-01", []), ("2026-10-30", [("rent", "2026-10", True)])],
)
async def test_a_lease_that_has_not_started_ends_today_and_owes_back_what_was_paid(
    database: Database, request: pytest.FixtureRequest, start: str, rents: list[object]
) -> None:
    with client_for(database, request) as client:
        ahead = {"start_date": start, "control_from_period": start[:7], "end_date": None}
        lease_id = start_lease(client, **ahead)
        paid = {"id": str(uuid7()), "amount_cents": 80_000, "received_on": "2026-10-20"}
        payments = f"/api/app/leases/{lease_id}/payments"
        assert send(client, "POST", payments, {**paid, "method": "yape"}).status_code == 201
        yesterday = terminate(client, lease_id, ended_on="2026-10-26")
        ended = terminate(client, lease_id, ended_on="2026-10-27")
        statement = client.get(f"/api/app/leases/{lease_id}/statement").json()

    assert (yesterday.status_code, yesterday.json()["detail"]) == (422, "end_before_start")
    assert (ended.status_code, ended.json()["ended_at"]) == (200, "2026-10-27")
    assert [(c["kind"], c["period"], c["voided"]) for c in statement["charges"]] == rents
    assert statement["credit_cents"] == 80_000
