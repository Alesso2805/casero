import hashlib
from datetime import UTC, date, datetime
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


def send(client: TestClient, method: str, path: str, body: object = None) -> Any:
    return client.request(method, path, json=body, headers={"X-CSRF-Token": client.cookies[CSRF]})


def start_lease(client: TestClient) -> str:
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
    }
    assert send(client, "POST", "/api/app/leases", lease).status_code == 201
    return str(lease["id"])


def client_for(database: Database, request: pytest.FixtureRequest) -> Any:
    return api_client(
        database, address_for(request.node.name), FixedClock(NOW), registration_mode="open"
    )


async def connect(database: Database, role: str) -> asyncpg.Connection:
    return await asyncpg.connect(database.dsn(role))


def token_of(url: str) -> str:
    prefix = "https://casero.example/i#t="
    assert url.startswith(prefix)
    return url.removeprefix(prefix)


async def test_a_link_is_shown_again_replaced_and_revoked(
    database: Database, request: pytest.FixtureRequest
) -> None:
    path_of = "/api/app/leases/{}/tenant-link"
    with client_for(database, request) as client:
        lease_id = start_lease(client)
        path = path_of.format(lease_id)
        none_yet = client.get(path).json()
        issued = send(client, "POST", path)
        shown = client.get(path).json()
        replaced = send(client, "POST", path).json()
        revoked = send(client, "POST", f"{path}/revoke")
        again = send(client, "POST", f"{path}/revoke")
        after = client.get(path).json()

    first_token = token_of(issued.json()["url"])
    assert none_yet == {"link": None}
    assert issued.status_code == 201
    assert shown["link"]["url"] == issued.json()["url"]
    assert token_of(replaced["url"]) != first_token
    assert (revoked.json(), again.status_code, after) == ({"link": None}, 200, {"link": None})
    owner = await connect(database, "casero_owner")
    try:
        rows = await owner.fetch(
            "SELECT nonce, token_hash, revoked_at FROM tenant_links WHERE lease_id = $1"
            " ORDER BY created_at, id",
            UUID(lease_id),
        )
    finally:
        await owner.close()
    assert len(rows) == 2
    assert all(row["revoked_at"] is not None for row in rows)
    assert rows[0]["token_hash"] == hashlib.sha256(first_token.encode()).digest()
    assert first_token.encode() not in b"".join(bytes(row["nonce"]) for row in rows)


async def test_the_database_resolves_the_link_from_the_hash_of_its_token(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with client_for(database, request) as client:
        lease_id = start_lease(client)
        url = send(client, "POST", f"/api/app/leases/{lease_id}/tenant-link").json()["url"]

    app = await connect(database, "casero_app")
    try:
        resolved = await app.fetch(
            "SELECT lease_id FROM app_resolve_tenant_token($1, $2)",
            hashlib.sha256(token_of(url).encode()).digest(),
            date(2026, 10, 27),
        )
    finally:
        await app.close()
    assert [str(row["lease_id"]) for row in resolved] == [lease_id]


async def test_another_account_or_a_lease_without_the_portal_gets_no_link(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with client_for(database, request) as ana, client_for(database, request) as luis:
        lease_id = start_lease(ana)
        start_lease(luis)
        path = f"/api/app/leases/{lease_id}/tenant-link"
        foreign = [luis.get(path), send(luis, "POST", path), send(luis, "POST", f"{path}/revoke")]
        owner = await connect(database, "casero_owner")
        try:
            await owner.execute(
                "UPDATE leases SET tools_enabled = false WHERE id = $1", UUID(lease_id)
            )
        finally:
            await owner.close()
        without_portal = send(ana, "POST", path)

    assert [(r.status_code, r.json()["detail"]) for r in foreign] == [(404, "lease_not_found")] * 3
    assert (without_portal.status_code, without_portal.json()["detail"]) == (
        403,
        "portal_unavailable",
    )
