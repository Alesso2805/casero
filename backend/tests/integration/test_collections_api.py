import time
from datetime import UTC, datetime
from statistics import quantiles
from typing import Any
from uuid import uuid7

import pytest
from fastapi.testclient import TestClient

from api_client import FixedClock, address_for, api_client
from database import Database

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 27, 15, 0, tzinfo=UTC)
CSRF = "__Host-casero_csrf"
PANEL_BUDGET_SECONDS = 1.0
PANEL_SAMPLES = 40


def send(client: TestClient, method: str, path: str, body: object = None) -> Any:
    return client.request(method, path, json=body, headers={"X-CSRF-Token": client.cookies[CSRF]})


def register(client: TestClient) -> None:
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


def start_leases(client: TestClient, *terms: dict[str, object]) -> list[str]:
    units = [{"name": f"Cuarto {n}", "kind": "room"} for n in range(len(terms))]
    house = send(
        client, "POST", "/api/app/properties", {"name": "Casa", "ownership": "sole", "units": units}
    ).json()
    renter = send(client, "POST", "/api/app/renters", {"full_name": "Ana"}).json()
    ids = []
    for unit, overrides in zip(house["units"], terms, strict=True):
        lease = {
            "id": str(uuid7()),
            "unit_id": unit["id"],
            "renter_id": renter["id"],
            "monthly_rent_cents": 80_000,
            "due_day": 5,
            "start_date": "2026-03-01",
            "control_from_period": "2026-09",
            "tax_treatment": "standard",
            **overrides,
        }
        assert send(client, "POST", "/api/app/leases", lease).status_code == 201
        ids.append(str(lease["id"]))
    return ids


def pay(client: TestClient, lease_id: str, cents: int, on: str) -> None:
    body = {"id": str(uuid7()), "amount_cents": cents, "received_on": on, "method": "yape"}
    assert send(client, "POST", f"/api/app/leases/{lease_id}/payments", body).status_code == 201


def client_for(database: Database, request: pytest.FixtureRequest) -> Any:
    return api_client(
        database, address_for(request.node.name), FixedClock(NOW), registration_mode="open"
    )


async def test_the_panel_lists_the_most_urgent_first_with_the_month_total(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with client_for(database, request) as ana, client_for(database, request) as luis:
        register(ana)
        later, overdue, today = start_leases(
            ana,
            {"due_day": 29, "control_from_period": "2026-10"},
            {},
            {"due_day": 27, "control_from_period": "2026-10"},
        )
        pay(ana, overdue, 50_000, "2026-09-06")
        panel = ana.get("/api/app/collections").json()
        register(luis)
        start_leases(luis, {})
        other = luis.get("/api/app/collections").json()

    assert [
        (line["lease_id"], line["status"], line["overdue_days"], line["overdue_cents"])
        for line in panel["leases"]
    ] == [
        (overdue, "overdue", 52, 110_000),
        (today, "due_today", 0, 0),
        (later, "due_soon", 0, 0),
    ]
    assert (panel["leases"][1]["next_due_on"], panel["leases"][1]["next_due_cents"]) == (
        "2026-10-27",
        80_000,
    )
    assert (panel["due_by_month_end_cents"], panel["overdue_cents"]) == (270_000, 110_000)
    assert overdue not in {line["lease_id"] for line in other["leases"]}
    assert len(other["leases"]) == 1


async def test_the_panel_needs_a_session(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with client_for(database, request) as client:
        response = client.get("/api/app/collections")

    assert response.status_code == 401


async def test_the_panel_answers_within_a_second_at_p95_with_ten_leases(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with client_for(database, request) as client:
        register(client)
        since_january: dict[str, object] = {
            "start_date": "2026-01-01",
            "control_from_period": "2026-01",
        }
        leases = start_leases(client, *[since_january] * 10)
        for lease_id in leases:
            for month in range(1, 11):
                pay(client, lease_id, 80_000, f"2026-{month:02d}-05")
        durations = []
        for _ in range(PANEL_SAMPLES):
            started = time.perf_counter()
            response = client.get("/api/app/collections")
            durations.append(time.perf_counter() - started)
            assert response.status_code == 200

    assert len(response.json()["leases"]) == 10
    assert quantiles(durations, n=20)[-1] < PANEL_BUDGET_SECONDS
