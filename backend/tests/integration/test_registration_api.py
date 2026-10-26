from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import uuid7

import asyncpg
import pytest
from fastapi.testclient import TestClient

from api_client import FixedClock, address_for, api_client
from casero.accounts.infrastructure.invites import create_invite
from database import Database

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 26, 15, 0, tzinfo=UTC)
PASSWORD = "una clave bien larga"


def admin_url(database: Database) -> str:
    return database.dsn("casero_admin").replace("postgresql://", "postgresql+asyncpg://", 1)


async def invite(database: Database, email: str) -> str:
    link = await create_invite(admin_url(database), email, "https://casero.example", NOW)
    return link.split("#invitacion=", 1)[1]


def body(email: str, token: str | None = None, **changes: Any) -> dict[str, Any]:
    return {
        "email": email,
        "password": PASSWORD,
        "display_name": "Ana Quispe",
        "invite_token": token,
        "accept_terms_and_privacy": True,
        "consent_sensitive_data": True,
        **changes,
    }


def post(client: TestClient, payload: dict[str, Any]) -> int:
    client.get("/api/public/csrf")
    response = client.post(
        "/api/public/registration",
        json=payload,
        headers={"X-CSRF-Token": client.cookies["__Host-casero_csrf"]},
    )
    return response.status_code


async def owner_fetch(database: Database, query: str, *args: Any) -> list[asyncpg.Record]:
    owner = await asyncpg.connect(database.dsn("casero_owner"))
    try:
        return await owner.fetch(query, *args)
    finally:
        await owner.close()


async def test_an_invited_landlord_registers_and_is_signed_in(
    database: Database, request: pytest.FixtureRequest
) -> None:
    email = f"{uuid7()}@example.com"
    await owner_fetch(
        database,
        "INSERT INTO waitlist_entries (id, email, source, consented_at, created_at)"
        " VALUES ($1, $2, 'landing', $3, $3) RETURNING id",
        uuid7(),
        email,
        NOW,
    )
    token = await invite(database, email.upper())

    with api_client(
        database, address_for(request.node.name), FixedClock(NOW), registration_mode="invite"
    ) as client:
        status = post(client, body(email, token))
        me = client.get("/api/app/me")
        again = post(client, body(f"{uuid7()}@example.com", token))

    assert status == 201
    assert me.json()["email"] == email
    [account] = await owner_fetch(
        database,
        "SELECT a.id, a.display_name, s.plan_code, s.starts_at, s.trial_ends_at, s.ends_at"
        " FROM accounts a JOIN account_members m ON m.account_id = a.id"
        " JOIN users u ON u.id = m.user_id JOIN subscriptions s ON s.account_id = a.id"
        " WHERE u.email = $1",
        email,
    )
    assert account["display_name"] == "Ana Quispe"
    assert account["plan_code"] == "casero"
    assert account["starts_at"] == date(2026, 10, 26)
    assert account["trial_ends_at"] == account["ends_at"] == date(2026, 11, 25)
    acceptances = await owner_fetch(
        database,
        "SELECT d.kind, octet_length(a.ip_hash) AS ip_hash FROM legal_acceptances a"
        " JOIN legal_documents d ON d.id = a.document_id WHERE a.account_id = $1 ORDER BY d.kind",
        account["id"],
    )
    assert [(row["kind"], row["ip_hash"]) for row in acceptances] == [
        ("privacy", 32),
        ("sensitive_consent", 32),
        ("terms", 32),
    ]
    assert (
        await owner_fetch(database, "SELECT 1 FROM waitlist_entries WHERE email = $1", email) == []
    )
    assert again == 403


async def test_an_invite_only_works_for_its_email_and_until_it_expires(
    database: Database, request: pytest.FixtureRequest
) -> None:
    email = f"{uuid7()}@example.com"
    token = await invite(database, email)
    late = FixedClock(NOW + timedelta(days=15))

    with api_client(database, address_for(request.node.name), registration_mode="invite") as client:
        other_email = post(client, body(f"{uuid7()}@example.com", token))
        no_token = post(client, body(email))
    with api_client(
        database, address_for(request.node.name), late, registration_mode="invite"
    ) as client:
        expired = post(client, body(email, token))

    assert (other_email, no_token, expired) == (403, 403, 403)


async def test_open_and_closed_registration(
    database: Database, request: pytest.FixtureRequest
) -> None:
    email = f"{uuid7()}@example.com"

    with api_client(database, address_for(request.node.name), registration_mode="closed") as client:
        closed = post(client, body(email))
    with api_client(database, address_for(request.node.name), registration_mode="open") as client:
        opened = post(client, body(email))
        taken = post(client, body(email.upper()))

    assert (closed, opened, taken) == (403, 201, 409)


@pytest.mark.parametrize(
    "changes",
    [
        {"password": "corta1234"},
        {"consent_sensitive_data": False},
        {"accept_terms_and_privacy": False},
        {"display_name": "   "},
    ],
)
def test_incomplete_registrations_are_rejected(
    database: Database, request: pytest.FixtureRequest, changes: dict[str, Any]
) -> None:
    with api_client(database, address_for(request.node.name), registration_mode="open") as client:
        assert post(client, body(f"{uuid7()}@example.com", **changes)) == 422


def test_registration_needs_the_csrf_token(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with api_client(database, address_for(request.node.name), registration_mode="open") as client:
        response = client.post("/api/public/registration", json=body(f"{uuid7()}@example.com"))

    assert response.status_code == 403


async def test_creating_an_invite_is_audited(database: Database) -> None:
    await invite(database, f"{uuid7()}@example.com")

    rows = await owner_fetch(
        database,
        "SELECT actor, staff_user_id FROM staff_audit_log WHERE action = 'invite.create'",
    )
    assert rows
    assert all((row["actor"], row["staff_user_id"]) == ("cli", None) for row in rows)
