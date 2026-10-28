from datetime import UTC, datetime
from typing import Any
from uuid import uuid7

import asyncpg
import pytest
from fastapi.testclient import TestClient

from api_client import (
    TEST_DOCUMENT_HASHER,
    TEST_FIELD_CIPHER,
    FixedClock,
    address_for,
    api_client,
)
from casero.shared.infrastructure.crypto import field_context
from database import Database

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 27, 15, 0, tzinfo=UTC)
CSRF = "__Host-casero_csrf"
DNI = "45678912"
ANA: dict[str, Any] = {
    "full_name": "Ana Quispe",
    "phone": "987 654 321",
    "document": {"doc_type": "dni", "number": DNI},
}


def register(client: TestClient, email: str) -> None:
    client.get("/api/public/csrf")
    response = client.post(
        "/api/public/registration",
        json={
            "email": email,
            "password": "una clave bien larga",
            "display_name": "Casera",
            "accept_terms_and_privacy": True,
            "consent_sensitive_data": True,
        },
        headers={"X-CSRF-Token": client.cookies[CSRF]},
    )
    assert response.status_code == 201


def send(client: TestClient, method: str, path: str, body: object) -> Any:
    return client.request(method, path, json=body, headers={"X-CSRF-Token": client.cookies[CSRF]})


async def owner_fetch(database: Database, query: str, *args: object) -> list[asyncpg.Record]:
    owner = await asyncpg.connect(database.dsn("casero_owner"))
    try:
        return await owner.fetch(query, *args)
    finally:
        await owner.close()


async def test_a_renter_is_stored_with_the_document_encrypted(
    database: Database, request: pytest.FixtureRequest
) -> None:
    email = f"{uuid7()}@example.com"
    with api_client(
        database, address_for(request.node.name), FixedClock(NOW), registration_mode="open"
    ) as client:
        register(client, email)
        created = send(client, "POST", "/api/app/renters", ANA)
        listed = client.get("/api/app/renters").json()

    assert created.status_code == 201
    renter = created.json()
    assert renter == {
        "id": renter["id"],
        "full_name": "Ana Quispe",
        "phone_e164": "+51987654321",
        "doc_type": "dni",
        "doc_last4": "8912",
    }
    assert listed == [renter]
    [row] = await owner_fetch(
        database,
        "SELECT account_id, doc_enc, doc_hmac, doc_last4 FROM renters WHERE id = $1::uuid",
        renter["id"],
    )
    context = field_context("renters", "doc_enc", row["account_id"])
    assert DNI not in row["doc_enc"]
    assert TEST_FIELD_CIPHER.decrypt(row["doc_enc"], context) == DNI
    assert row["doc_hmac"] == TEST_DOCUMENT_HASHER.digest("dni", DNI)
    audit = await owner_fetch(
        database,
        "SELECT a.* FROM audit_log a JOIN users u ON u.id = a.actor_user_id WHERE u.email = $1",
        email,
    )
    assert [list(entry["changed_fields"]) for entry in audit] == [
        ["full_name", "phone_e164", "document"]
    ]
    assert DNI not in repr([dict(entry) for entry in audit])


async def test_the_same_document_is_one_renter_per_account(
    database: Database, request: pytest.FixtureRequest
) -> None:
    clock = FixedClock(NOW)
    with (
        api_client(
            database, address_for(request.node.name), clock, registration_mode="open"
        ) as ana,
        api_client(
            database, address_for(request.node.name), clock, registration_mode="open"
        ) as luis,
    ):
        register(ana, f"{uuid7()}@example.com")
        register(luis, f"{uuid7()}@example.com")
        first = send(ana, "POST", "/api/app/renters", ANA)
        again = send(
            ana,
            "POST",
            "/api/app/renters",
            {**ANA, "full_name": "Ana", "document": {"doc_type": "dni", "number": "4567-8912"}},
        )
        other_account = send(luis, "POST", "/api/app/renters", ANA)

    assert first.status_code == 201
    assert (again.status_code, again.json()["detail"]) == (409, "duplicate_document")
    assert other_account.status_code == 201


@pytest.mark.parametrize(
    ("overrides", "detail"),
    [
        ({"phone": "12345"}, "invalid_phone"),
        ({"document": {"doc_type": "dni", "number": "1234567"}}, "invalid_document"),
        ({"document": {"doc_type": "ruc", "number": "20131312954"}}, "invalid_document"),
        ({"full_name": " "}, None),
        ({"document": {"doc_type": "license", "number": "12345678"}}, None),
    ],
)
async def test_invalid_renters_are_refused(
    database: Database,
    request: pytest.FixtureRequest,
    overrides: dict[str, object],
    detail: str | None,
) -> None:
    with api_client(
        database, address_for(request.node.name), FixedClock(NOW), registration_mode="open"
    ) as client:
        register(client, f"{uuid7()}@example.com")
        response = send(client, "POST", "/api/app/renters", {**ANA, **overrides})
        listed = client.get("/api/app/renters").json()

    assert response.status_code == 422
    if detail is not None:
        assert response.json()["detail"] == detail
    assert listed == []


async def test_a_renter_is_edited_and_gets_a_document_later(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with api_client(
        database, address_for(request.node.name), FixedClock(NOW), registration_mode="open"
    ) as client:
        register(client, f"{uuid7()}@example.com")
        ana = send(client, "POST", "/api/app/renters", ANA).json()
        luis = send(client, "POST", "/api/app/renters", {"full_name": "Luis"}).json()
        renamed = send(
            client, "PUT", f"/api/app/renters/{ana['id']}", {"full_name": "Ana María Quispe"}
        )
        documented = send(
            client,
            "PUT",
            f"/api/app/renters/{luis['id']}",
            {"full_name": "Luis", "document": {"doc_type": "ruc", "number": "20131312955"}},
        )
        taken = send(
            client,
            "PUT",
            f"/api/app/renters/{luis['id']}",
            {"full_name": "Luis", "document": ANA["document"]},
        )

    assert renamed.json() == {
        **ana,
        "full_name": "Ana María Quispe",
        "phone_e164": None,
    }
    assert (documented.json()["doc_type"], documented.json()["doc_last4"]) == ("ruc", "2955")
    assert (taken.status_code, taken.json()["detail"]) == (409, "duplicate_document")


async def test_each_landlord_sees_and_edits_only_their_own_renters(
    database: Database, request: pytest.FixtureRequest
) -> None:
    clock = FixedClock(NOW)
    with (
        api_client(
            database, address_for(request.node.name), clock, registration_mode="open"
        ) as ana,
        api_client(
            database, address_for(request.node.name), clock, registration_mode="open"
        ) as luis,
    ):
        register(ana, f"{uuid7()}@example.com")
        register(luis, f"{uuid7()}@example.com")
        renter = send(ana, "POST", "/api/app/renters", ANA).json()
        intrusion = send(luis, "PUT", f"/api/app/renters/{renter['id']}", {"full_name": "X"})
        luis_list = luis.get("/api/app/renters").json()

    assert intrusion.status_code == 404
    assert luis_list == []


async def test_writes_need_the_csrf_token(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with api_client(
        database, address_for(request.node.name), FixedClock(NOW), registration_mode="open"
    ) as client:
        register(client, f"{uuid7()}@example.com")
        response = client.post("/api/app/renters", json=ANA)

    assert (response.status_code, response.json()["detail"]) == (403, "csrf")


def test_renters_need_a_session(database: Database, request: pytest.FixtureRequest) -> None:
    with api_client(database, address_for(request.node.name)) as client:
        assert client.get("/api/app/renters").status_code == 401
