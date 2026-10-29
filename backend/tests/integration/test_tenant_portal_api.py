from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid7

import asyncpg
import pytest
from fastapi.testclient import TestClient

from api_client import FixedClock, address_for, api_client
from database import Database

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 27, 15, 0, tzinfo=UTC)
CSRF = "__Host-casero_csrf"
RUC = "10456789012"
PRIVATE_NOTE = "Pagó tarde, ojo con este inquilino"
STATEMENT = "/api/tenant/statement"


def send(client: TestClient, method: str, path: str, body: object = None) -> Any:
    return client.request(method, path, json=body, headers={"X-CSRF-Token": client.cookies[CSRF]})


def start_lease(client: TestClient, email: str) -> str:
    client.get("/api/public/csrf")
    registered = send(
        client,
        "POST",
        "/api/public/registration",
        {
            "email": email,
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
    }
    assert send(client, "POST", "/api/app/leases", lease).status_code == 201
    return str(lease["id"])


def issue_link(client: TestClient, lease_id: str) -> str:
    url: str = send(client, "POST", f"/api/app/leases/{lease_id}/tenant-link").json()["url"]
    return url.split("#t=", 1)[1]


def portal(client: TestClient, token: str) -> Any:
    return client.get(STATEMENT, headers={"X-Tenant-Token": token})


async def owner_execute(database: Database, query: str, *args: object) -> list[asyncpg.Record]:
    owner = await asyncpg.connect(database.dsn("casero_owner"))
    try:
        return await owner.fetch(query, *args)
    finally:
        await owner.close()


def client_for(database: Database, request: pytest.FixtureRequest) -> Any:
    return api_client(
        database, address_for(request.node.name), FixedClock(NOW), registration_mode="open"
    )


async def test_the_tenant_sees_its_balance_and_history_but_nothing_private(
    database: Database, request: pytest.FixtureRequest
) -> None:
    email = f"{uuid7()}@example.com"
    with client_for(database, request) as client:
        lease_id = start_lease(client, email)
        await owner_execute(
            database,
            "UPDATE accounts SET ruc = $1, ruc_group = '2-3'"
            " WHERE id = (SELECT account_id FROM leases WHERE id = $2)",
            RUC,
            UUID(lease_id),
        )
        payment = {
            "id": str(uuid7()),
            "amount_cents": 50_000,
            "received_on": "2026-10-10",
            "method": "yape",
            "note": PRIVATE_NOTE,
        }
        send(client, "POST", f"/api/app/leases/{lease_id}/payments", payment)
        token = issue_link(client, lease_id)
        client.cookies.clear()
        response = portal(client, token)

    body = response.json()
    assert response.status_code == 200
    assert (body["landlord_name"], body["renter_name"], body["unit"]) == (
        "Casera",
        "Ana",
        "Cuarto · Casa",
    )
    assert body["balance_cents"] == 110_000
    assert body["payments"] == [
        {"amount_cents": 50_000, "received_on": "2026-10-10", "method": "yape", "voided": False}
    ]
    for private in (RUC, email, PRIVATE_NOTE, token):
        assert private not in response.text
    [link] = await owner_execute(
        database, "SELECT last_used_at FROM tenant_links WHERE lease_id = $1", UUID(lease_id)
    )
    assert link["last_used_at"] == NOW


async def test_a_wrong_revoked_or_disabled_link_opens_nothing(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with client_for(database, request) as client:
        lease_id = start_lease(client, f"{uuid7()}@example.com")
        revoked = issue_link(client, lease_id)
        token = issue_link(client, lease_id)
        answers = [
            portal(client, "x" * 43),
            portal(client, "not a token"),
            client.get(STATEMENT),
            portal(client, revoked),
        ]
        await owner_execute(
            database, "UPDATE leases SET tools_enabled = false WHERE id = $1", UUID(lease_id)
        )
        disabled = portal(client, token)

    assert [(a.status_code, a.json()["detail"]) for a in answers] == [(404, "link_not_found")] * 4
    assert (disabled.status_code, disabled.json()["detail"]) == (403, "portal_unavailable")


async def test_guessing_tokens_is_limited_per_client(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with client_for(database, request) as client:
        answers = [portal(client, "y" * 43).status_code for _ in range(61)]

    assert answers[:60] == [404] * 60
    assert answers[60] == 429
