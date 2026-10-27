from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid7

import asyncpg
import pytest
from fastapi.testclient import TestClient

from api_client import FixedClock, address_for, api_client
from database import Database

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 26, 15, 0, tzinfo=UTC)
CSRF = "__Host-casero_csrf"


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


async def test_each_landlord_sees_only_their_own_account(
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
        ana_account = ana.get("/api/app/account").json()
        luis_account = luis.get("/api/app/account").json()

    assert ana_account["display_name"] == "Ana"
    assert luis_account["display_name"] == "Luis"
    assert ana_account == {
        "display_name": "Ana",
        "plan_code": "casero",
        "status": "trial",
        "trial_ends_at": "2026-11-25",
        "ends_at": "2026-11-25",
        "max_active_leases": 10,
        "features": {
            "whatsapp_links": True,
            "tenant_portal": True,
            "tax_module": True,
            "tax_reminders": True,
            "receipts_pdf": True,
            "accountant_export": True,
            "data_export": True,
        },
    }


async def test_after_the_trial_and_its_grace_the_account_is_on_the_free_plan(
    database: Database, request: pytest.FixtureRequest
) -> None:
    clock = FixedClock(NOW)
    email = f"{uuid7()}@example.com"
    with api_client(
        database, address_for(request.node.name), clock, registration_mode="open"
    ) as client:
        register(client, email, "Ana")
        owner = await asyncpg.connect(database.dsn("casero_owner"))
        try:
            await owner.execute(
                "UPDATE users SET email_verified_at = $1 WHERE email = $2", NOW, email
            )
        finally:
            await owner.close()
        clock.advance(timedelta(days=29))
        in_trial = client.get("/api/app/account").json()
        clock.advance(timedelta(days=8))
        lapsed = client.get("/api/app/account").json()

    assert (in_trial["plan_code"], in_trial["status"]) == ("casero", "trial")
    assert (lapsed["plan_code"], lapsed["status"]) == ("free", "free")
    assert lapsed["max_active_leases"] == 1
    assert lapsed["features"]["tax_module"] is False


async def test_an_unverified_account_is_paused_after_seven_days(
    database: Database, request: pytest.FixtureRequest
) -> None:
    clock = FixedClock(NOW)
    with api_client(
        database, address_for(request.node.name), clock, registration_mode="open"
    ) as client:
        register(client, f"{uuid7()}@example.com", "Ana")
        before = client.get("/api/app/account").status_code
        clock.advance(timedelta(days=7))
        after = client.get("/api/app/account")
        me = client.get("/api/app/me").status_code

    assert before == 200
    assert (after.status_code, after.json()["detail"]) == (403, "email_unverified")
    assert me == 200


def test_the_account_needs_a_session(database: Database, request: pytest.FixtureRequest) -> None:
    with api_client(database, address_for(request.node.name)) as client:
        assert client.get("/api/app/account").status_code == 401
