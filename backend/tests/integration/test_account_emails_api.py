from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid7

import pytest
from fastapi.testclient import TestClient

from api_client import FixedClock, RecordingMailer, address_for, api_client
from database import Database

pytestmark = pytest.mark.anyio

PASSWORD = "una clave bien larga"
CSRF = "__Host-casero_csrf"


def csrf(client: TestClient) -> dict[str, str]:
    if CSRF not in client.cookies:
        client.get("/api/public/csrf")
    return {"X-CSRF-Token": client.cookies[CSRF]}


def register(client: TestClient, email: str) -> int:
    body: dict[str, Any] = {
        "email": email,
        "password": PASSWORD,
        "display_name": "Ana",
        "accept_terms_and_privacy": True,
        "consent_sensitive_data": True,
    }
    return client.post("/api/public/registration", json=body, headers=csrf(client)).status_code


def token_of(mailer: RecordingMailer, index: int = -1) -> str:
    return mailer.sent[index].text.split("#token=", 1)[1].split()[0]


async def test_registration_sends_a_verification_link_that_works_once(
    database: Database, request: pytest.FixtureRequest
) -> None:
    mailer = RecordingMailer()
    email = f"{uuid7()}@example.com"

    with api_client(
        database, address_for(request.node.name), registration_mode="open", mailer=mailer
    ) as client:
        assert register(client, email) == 201
        [message] = mailer.sent
        token = token_of(mailer)
        assert message.to == email
        assert client.get("/api/app/me").json()["email_verified"] is False
        first = client.post("/api/public/email-verification", json={"token": token})
        again = client.post("/api/public/email-verification", json={"token": token})
        me = client.get("/api/app/me").json()
        resend = client.post("/api/app/email-verification", headers=csrf(client))

    assert (first.status_code, again.status_code) == (204, 400)
    assert me["email_verified"] is True
    assert resend.status_code == 204


async def test_resending_is_limited_to_three_emails_an_hour(
    database: Database, request: pytest.FixtureRequest
) -> None:
    mailer = RecordingMailer()
    clock = FixedClock(datetime(2049, 2, 1, 15, 0, tzinfo=UTC))

    with api_client(
        database, address_for(request.node.name), clock, registration_mode="open", mailer=mailer
    ) as client:
        register(client, f"{uuid7()}@example.com")
        statuses = [
            client.post("/api/app/email-verification", headers=csrf(client)).status_code
            for _ in range(3)
        ]
        anonymous = TestClient(client.app, base_url="https://testserver")
        without_session = anonymous.post("/api/app/email-verification").status_code

    assert statuses == [202, 202, 429]
    assert len(mailer.sent) == 3
    assert without_session == 403


async def test_a_verification_link_expires_after_seven_days(
    database: Database, request: pytest.FixtureRequest
) -> None:
    mailer = RecordingMailer()
    clock = FixedClock(datetime(2026, 10, 26, 15, 0, tzinfo=UTC))

    with api_client(
        database, address_for(request.node.name), clock, registration_mode="open", mailer=mailer
    ) as client:
        register(client, f"{uuid7()}@example.com")
        clock.advance(timedelta(days=7, minutes=1))
        response = client.post("/api/public/email-verification", json={"token": token_of(mailer)})

    assert response.status_code == 400


async def test_a_password_reset_changes_the_password_and_signs_out_everywhere(
    database: Database, request: pytest.FixtureRequest
) -> None:
    mailer = RecordingMailer()
    email = f"{uuid7()}@example.com"
    new_password = "otra clave bien larga"

    with api_client(
        database, address_for(request.node.name), registration_mode="open", mailer=mailer
    ) as client:
        register(client, email)
        unknown = client.post("/api/public/password-reset", json={"email": "nadie@example.com"})
        known = client.post("/api/public/password-reset", json={"email": email.upper()})
        token = token_of(mailer)
        weak = client.post(
            "/api/public/password-reset/confirm", json={"token": token, "password": "corta"}
        )
        done = client.post(
            "/api/public/password-reset/confirm", json={"token": token, "password": new_password}
        )
        reused = client.post(
            "/api/public/password-reset/confirm", json={"token": token, "password": new_password}
        )
        signed_out = client.get("/api/app/me").status_code
        old = client.post(
            "/api/public/session", json={"email": email, "password": PASSWORD}, headers=csrf(client)
        )
        new = client.post(
            "/api/public/session",
            json={"email": email, "password": new_password},
            headers=csrf(client),
        )

    assert (unknown.status_code, known.status_code) == (202, 202)
    assert [message.subject for message in mailer.sent] == [
        "Confirma tu correo en Casero",
        "Cambia tu contraseña de Casero",
    ]
    assert (weak.status_code, done.status_code, reused.status_code) == (422, 204, 400)
    assert signed_out == 401
    assert (old.status_code, new.status_code) == (401, 204)


async def test_a_reset_link_expires_after_thirty_minutes(
    database: Database, request: pytest.FixtureRequest
) -> None:
    mailer = RecordingMailer()
    email = f"{uuid7()}@example.com"
    clock = FixedClock(datetime(2026, 10, 26, 15, 0, tzinfo=UTC))

    with api_client(
        database, address_for(request.node.name), clock, registration_mode="open", mailer=mailer
    ) as client:
        register(client, email)
        client.post("/api/public/password-reset", json={"email": email})
        clock.advance(timedelta(minutes=31))
        response = client.post(
            "/api/public/password-reset/confirm",
            json={"token": token_of(mailer), "password": "otra clave bien larga"},
        )

    assert response.status_code == 400


async def test_me_reports_the_verification_deadline_and_the_block(
    database: Database, request: pytest.FixtureRequest
) -> None:
    clock = FixedClock(datetime(2026, 10, 26, 15, 0, tzinfo=UTC))

    with api_client(
        database, address_for(request.node.name), clock, registration_mode="open"
    ) as client:
        register(client, f"{uuid7()}@example.com")
        fresh = client.get("/api/app/me").json()
        clock.advance(timedelta(days=8))
        late = client.get("/api/app/me").json()

    assert fresh["verify_by"] == "2026-11-02T15:00:00Z"
    assert fresh["blocked_until_verified"] is False
    assert late["blocked_until_verified"] is True
