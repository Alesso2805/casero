from datetime import UTC, datetime
from typing import Any
from uuid import uuid7

import asyncpg
import pytest
from fastapi.testclient import TestClient

from api_client import TEST_EMAIL_HASH_KEY, FixedClock, address_for, api_client
from casero.identity.infrastructure.email_suppressions import email_hash
from database import Database

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 27, 15, 0, tzinfo=UTC)
CSRF = "__Host-casero_csrf"
SUNAT_RUC = "20131312955"


def register(client: TestClient, email: str, name: str) -> None:
    client.get("/api/public/csrf")
    body: dict[str, Any] = {
        "email": email,
        "password": "una clave bien larga",
        "display_name": name,
        "accept_terms_and_privacy": True,
        "consent_sensitive_data": True,
    }
    response = client.post(
        "/api/public/registration", json=body, headers={"X-CSRF-Token": client.cookies[CSRF]}
    )
    assert response.status_code == 201


def put_profile(client: TestClient, **overrides: object) -> Any:
    body: dict[str, object] = {
        "display_name": "Ana Quispe",
        "taxpayer_kind": "person",
        "ruc": SUNAT_RUC,
        "good_taxpayer": False,
        "daily_digest": True,
    }
    return client.put(
        "/api/app/account/profile",
        json={**body, **overrides},
        headers={"X-CSRF-Token": client.cookies[CSRF]},
    )


async def audit_entries(database: Database, email: str) -> list[tuple[str, list[str]]]:
    owner = await asyncpg.connect(database.dsn("casero_owner"))
    try:
        rows = await owner.fetch(
            "SELECT a.action, a.changed_fields FROM audit_log a"
            " JOIN account_members m ON m.account_id = a.account_id"
            " JOIN users u ON u.id = m.user_id AND u.id = a.actor_user_id"
            " WHERE u.email = $1 ORDER BY a.id",
            email,
        )
    finally:
        await owner.close()
    return [(row["action"], list(row["changed_fields"])) for row in rows]


async def test_a_new_account_has_an_empty_tax_profile(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with api_client(
        database, address_for(request.node.name), FixedClock(NOW), registration_mode="open"
    ) as client:
        register(client, f"{uuid7()}@example.com", "Ana")
        profile = client.get("/api/app/account/profile")

    assert profile.json() == {
        "display_name": "Ana",
        "taxpayer_kind": "person",
        "ruc": None,
        "ruc_group": None,
        "daily_digest": False,
        "declarant_locked": False,
        "tax_reminders_email": True,
    }


async def test_the_landlord_saves_a_ruc_and_gets_its_schedule_group(
    database: Database, request: pytest.FixtureRequest
) -> None:
    email = f"{uuid7()}@example.com"
    with api_client(
        database, address_for(request.node.name), FixedClock(NOW), registration_mode="open"
    ) as client:
        register(client, email, "Ana")
        saved = put_profile(client)
        good = put_profile(client, good_taxpayer=True)
        read = client.get("/api/app/account/profile").json()
        account = client.get("/api/app/account").json()

    assert saved.status_code == 200
    assert saved.json()["ruc_group"] == "4-5"
    assert good.json()["ruc_group"] == "bc"
    assert read == {
        "display_name": "Ana Quispe",
        "taxpayer_kind": "person",
        "ruc": SUNAT_RUC,
        "ruc_group": "bc",
        "daily_digest": True,
        "declarant_locked": False,
        "tax_reminders_email": True,
    }
    assert account["display_name"] == "Ana Quispe"
    assert await audit_entries(database, email) == [
        ("account.profile_updated", ["display_name", "ruc", "ruc_group", "daily_digest"]),
        ("account.profile_updated", ["ruc_group"]),
    ]


async def suppressions(database: Database, *emails: str) -> list[tuple[str, str | None, str]]:
    hashes = {email_hash(TEST_EMAIL_HASH_KEY, email): email for email in emails}
    owner = await asyncpg.connect(database.dsn("casero_owner"))
    try:
        rows = await owner.fetch(
            "SELECT email_hash, email_kind, reason FROM email_suppressions"
            " WHERE email_hash = ANY($1::bytea[]) ORDER BY reason",
            list(hashes),
        )
    finally:
        await owner.close()
    return [(hashes[bytes(r["email_hash"])], r["email_kind"], r["reason"]) for r in rows]


async def suppress(database: Database, email: str, kind: str | None, reason: str) -> None:
    owner = await asyncpg.connect(database.dsn("casero_owner"))
    try:
        await owner.execute(
            "INSERT INTO email_suppressions (email_hash, email_kind, reason, created_at)"
            " VALUES ($1, $2, $3, $4)",
            email_hash(TEST_EMAIL_HASH_KEY, email),
            kind,
            reason,
            NOW,
        )
    finally:
        await owner.close()


async def test_mis_datos_undoes_only_the_users_own_unsubscribe_from_sunat_reminders(
    database: Database, request: pytest.FixtureRequest
) -> None:
    email, other = f"{uuid7()}@example.com", f"{uuid7()}@example.com"
    await suppress(database, other, "tax_reminders", "unsubscribe")
    with api_client(
        database, address_for(request.node.name), FixedClock(NOW), registration_mode="open"
    ) as client:
        register(client, email, "Ana")
        unsubscribed = put_profile(client, tax_reminders_email=False)
        await suppress(database, email, None, "bounce")
        left_out = put_profile(client)
        before = await suppressions(database, email, other)
        back = put_profile(client, tax_reminders_email=True)
        read = client.get("/api/app/account/profile").json()

    assert unsubscribed.json()["tax_reminders_email"] is False
    assert left_out.json()["tax_reminders_email"] is False
    assert set(before) == {
        (email, None, "bounce"),
        (email, "tax_reminders", "unsubscribe"),
        (other, "tax_reminders", "unsubscribe"),
    }
    assert (back.json()["tax_reminders_email"], read["tax_reminders_email"]) == (True, True)
    assert set(await suppressions(database, email, other)) == {
        (email, None, "bounce"),
        (other, "tax_reminders", "unsubscribe"),
    }
    assert [fields for _, fields in await audit_entries(database, email)] == [
        ["display_name", "ruc", "ruc_group", "daily_digest", "tax_reminders_email"],
        ["tax_reminders_email"],
    ]


@pytest.mark.parametrize(
    ("overrides", "detail"),
    [
        ({"ruc": "20131312954"}, "invalid_ruc"),
        ({"ruc": "2013131295"}, None),
        ({"taxpayer_kind": "company"}, None),
        ({"display_name": "  "}, None),
    ],
)
async def test_invalid_profiles_are_refused(
    database: Database,
    request: pytest.FixtureRequest,
    overrides: dict[str, object],
    detail: str | None,
) -> None:
    with api_client(
        database, address_for(request.node.name), FixedClock(NOW), registration_mode="open"
    ) as client:
        register(client, f"{uuid7()}@example.com", "Ana")
        response = put_profile(client, **overrides)
        profile = client.get("/api/app/account/profile").json()

    assert response.status_code == 422
    if detail is not None:
        assert response.json()["detail"] == detail
    assert profile["ruc"] is None


async def test_saving_needs_the_csrf_token(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with api_client(
        database, address_for(request.node.name), FixedClock(NOW), registration_mode="open"
    ) as client:
        register(client, f"{uuid7()}@example.com", "Ana")
        response = client.put(
            "/api/app/account/profile",
            json={
                "display_name": "Ana",
                "taxpayer_kind": "person",
                "ruc": None,
                "daily_digest": False,
            },
        )

    assert (response.status_code, response.json()["detail"]) == (403, "csrf")


async def test_each_landlord_edits_only_their_own_profile(
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
        register(ana, f"{uuid7()}@example.com", "Ana")
        register(luis, f"{uuid7()}@example.com", "Luis")
        put_profile(ana)
        luis_profile = luis.get("/api/app/account/profile").json()

    assert (luis_profile["display_name"], luis_profile["ruc"]) == ("Luis", None)


def test_the_profile_needs_a_session(database: Database, request: pytest.FixtureRequest) -> None:
    with api_client(database, address_for(request.node.name)) as client:
        assert client.get("/api/app/account/profile").status_code == 401
