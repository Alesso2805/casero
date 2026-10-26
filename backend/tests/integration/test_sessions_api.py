from datetime import UTC, datetime, timedelta
from uuid import uuid7

import asyncpg
import pytest
from fastapi.testclient import TestClient

from api_client import FixedClock, address_for, api_client
from casero.api import LOGIN_ATTEMPTS_PER_IP_PER_HOUR
from casero.identity.infrastructure.passwords import Argon2PasswordHasher
from database import Database

pytestmark = pytest.mark.anyio

PASSWORD = "una clave bien larga"
CSRF = "__Host-casero_csrf"
SESSION = "__Host-casero_session"


async def a_user(database: Database) -> str:
    email = f"{uuid7()}@example.com"
    owner = await asyncpg.connect(database.dsn("casero_owner"))
    try:
        await owner.execute(
            "INSERT INTO users (id, email, password_hash, created_at) VALUES ($1, $2, $3, $4)",
            uuid7(),
            email,
            await Argon2PasswordHasher().hash(PASSWORD),
            datetime(2026, 10, 26, tzinfo=UTC),
        )
    finally:
        await owner.close()
    return email


def csrf(client: TestClient) -> dict[str, str]:
    if CSRF not in client.cookies:
        client.get("/api/public/csrf")
    return {"X-CSRF-Token": client.cookies[CSRF]}


def log_in(client: TestClient, email: str, password: str = PASSWORD) -> int:
    response = client.post(
        "/api/public/session", json={"email": email, "password": password}, headers=csrf(client)
    )
    return response.status_code


class Sleeper:
    def __init__(self) -> None:
        self.slept: list[int] = []

    async def sleep(self, seconds: int) -> None:
        self.slept.append(seconds)


async def test_login_needs_the_csrf_token(
    database: Database, request: pytest.FixtureRequest
) -> None:
    email = await a_user(database)

    with api_client(database, address_for(request.node.name)) as client:
        client.get("/api/public/csrf")
        body = {"email": email, "password": PASSWORD}
        missing = client.post("/api/public/session", json=body)
        wrong = client.post("/api/public/session", json=body, headers={"X-CSRF-Token": "x"})

    assert (missing.status_code, wrong.status_code) == (403, 403)


async def test_a_session_opens_identifies_the_user_and_closes(
    database: Database, request: pytest.FixtureRequest
) -> None:
    email = await a_user(database)

    with api_client(database, address_for(request.node.name)) as client:
        assert log_in(client, email.upper()) == 204
        me = client.get("/api/app/me")
        logout = client.delete("/api/app/session", headers=csrf(client))
        after = client.get("/api/app/me")

    assert me.status_code == 200
    assert me.json()["email"] == email
    assert me.json()["email_verified"] is False
    assert logout.status_code == 204
    assert after.status_code == 401


async def test_wrong_credentials_are_refused(
    database: Database, request: pytest.FixtureRequest
) -> None:
    email = await a_user(database)

    with api_client(database, address_for(request.node.name)) as client:
        assert log_in(client, email, "otra clave cualquiera") == 401
        assert log_in(client, "nadie@example.com") == 401
        assert client.get("/api/app/me").status_code == 401


async def test_logging_in_again_rotates_the_session(
    database: Database, request: pytest.FixtureRequest
) -> None:
    email = await a_user(database)

    with (
        api_client(database, address_for(request.node.name)) as client,
        api_client(database, address_for(request.node.name)) as stale,
    ):
        log_in(client, email)
        first = client.cookies[SESSION]
        log_in(client, email)
        stale.cookies.set(SESSION, first)

        assert client.cookies[SESSION] != first
        assert client.get("/api/app/me").status_code == 200
        assert stale.get("/api/app/me").status_code == 401


async def test_closing_all_sessions_signs_out_other_devices(
    database: Database, request: pytest.FixtureRequest
) -> None:
    email = await a_user(database)

    with (
        api_client(database, address_for(request.node.name)) as phone,
        api_client(database, address_for(request.node.name)) as laptop,
    ):
        log_in(phone, email)
        log_in(laptop, email)
        assert phone.delete("/api/app/sessions", headers=csrf(phone)).status_code == 204
        assert laptop.get("/api/app/me").status_code == 401


async def test_an_idle_session_expires_after_thirty_days(
    database: Database, request: pytest.FixtureRequest
) -> None:
    email = await a_user(database)
    clock = FixedClock(datetime(2026, 10, 26, 15, 0, tzinfo=UTC))

    with api_client(database, address_for(request.node.name), clock) as client:
        log_in(client, email)
        clock.advance(timedelta(days=29))
        still_there = client.get("/api/app/me").status_code
        clock.advance(timedelta(days=29))
        slid = client.get("/api/app/me").status_code
        clock.advance(timedelta(days=31))
        expired = client.get("/api/app/me").status_code

    assert (still_there, slid, expired) == (200, 200, 401)


async def test_an_ip_is_blocked_and_an_email_slowed_down(
    database: Database, request: pytest.FixtureRequest
) -> None:
    email = await a_user(database)
    sleeper = Sleeper()
    clock = FixedClock(datetime(2048, 1, 1, 15, 0, tzinfo=UTC))

    with api_client(database, address_for(request.node.name), clock, sleeper=sleeper) as client:
        statuses = [
            log_in(client, email, "otra clave cualquiera")
            for _ in range(LOGIN_ATTEMPTS_PER_IP_PER_HOUR + 1)
        ]

    assert statuses == [401] * LOGIN_ATTEMPTS_PER_IP_PER_HOUR + [429]
    assert sleeper.slept[:4] == [1, 2, 4, 8]
    assert max(sleeper.slept) == 30
