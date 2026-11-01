import re
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid7

import asyncpg
import pytest
from fastapi.testclient import TestClient

from api_client import (
    TEST_EMAIL_HASH_KEY,
    FixedClock,
    RecordingMailer,
    address_for,
    api_client,
)
from casero.identity.infrastructure.email_suppressions import email_hash
from casero.shared.kernel.email import Email, MailDeliveryError
from database import Database
from tax_flows import register, send

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 27, 15, 0, tzinfo=UTC)
DELETION = "/api/app/account/deletion"
CANCELLATION = "/api/public/account-deletion/cancellation"
PASSWORD = "una clave bien larga"


class FailingMailer:
    async def send(self, email: Email) -> None:
        raise MailDeliveryError("down")


def client_with(
    database: Database, request: pytest.FixtureRequest, mailer: Any, clock: FixedClock | None = None
) -> Any:
    return api_client(
        database,
        address_for(request.node.name),
        clock or FixedClock(NOW),
        registration_mode="open",
        mailer=mailer,
    )


def log_in(client: TestClient, email: str) -> Any:
    client.get("/api/public/csrf")
    return send(client, "POST", "/api/public/session", {"email": email, "password": PASSWORD})


async def owner_row(database: Database, query: str, *args: object) -> Any:
    owner = await asyncpg.connect(database.dsn("casero_owner"))
    try:
        return await owner.fetchrow(query, *args)
    finally:
        await owner.close()


async def account_of(database: Database, user_id: UUID) -> Any:
    return await owner_row(
        database,
        "SELECT a.* FROM accounts a JOIN account_members m ON m.account_id = a.id"
        " WHERE m.user_id = $1",
        user_id,
    )


async def user_id_of(database: Database, email: str) -> UUID:
    row = await owner_row(database, "SELECT id FROM users WHERE email = $1", email)
    user_id: UUID = row["id"]
    return user_id


def token_in(email: Email) -> str:
    match = re.search(r"/cancelar-eliminacion#token=(\S+)", email.text)
    assert match is not None
    return match.group(1)


async def test_a_deletion_closes_the_account_and_its_link_brings_it_back(
    database: Database, request: pytest.FixtureRequest
) -> None:
    email = f"{uuid7()}@example.com"
    mailer = RecordingMailer()
    with client_with(database, request, mailer) as client:
        register(client, email)
        user_id = await user_id_of(database, email)
        await owner_row(
            database,
            "INSERT INTO registration_invites (id, email, token_hash, expires_at)"
            " VALUES ($1, $2, $3, $4)",
            uuid7(),
            email.upper(),
            uuid7().bytes * 2,
            NOW,
        )
        mailer.sent.clear()
        deleted = send(client, "POST", DELETION)
        cookie_left = "__Host-casero_session" in client.cookies
        me = client.get("/api/app/me")
        locked_out = log_in(client, email)
        user = await owner_row(
            database, "SELECT email, deleted_at FROM users WHERE id = $1", user_id
        )
        account = await account_of(database, user_id)
        invites = await owner_row(
            database,
            "SELECT count(*) AS n FROM registration_invites WHERE lower(email) = lower($1)",
            email,
        )
        token = token_in(mailer.sent[0])
        cancelled = client.post(CANCELLATION, json={"token": token})
        again = client.post(CANCELLATION, json={"token": token})
        back = log_in(client, email)
        restored = await owner_row(
            database, "SELECT email, deleted_at FROM users WHERE id = $1", user_id
        )
        account_back = await account_of(database, user_id)

    assert (deleted.status_code, deleted.json()) == (200, {"purge_on": "2026-11-26"})
    assert not cookie_left
    assert me.status_code == 401
    assert locked_out.status_code == 401
    assert user["email"] == f"deleted+{user_id}@invalid"
    assert user["deleted_at"] == NOW
    assert account["deletion_scheduled_for"] == date(2026, 11, 26)
    assert account["deletion_contact_enc"].startswith("v1:")
    assert email not in account["deletion_contact_enc"]
    assert invites["n"] == 0
    assert [sent.to for sent in mailer.sent] == [email]
    assert "26/11/2026" in mailer.sent[0].text
    assert (cancelled.status_code, again.status_code) == (204, 400)
    assert back.status_code == 204
    assert (restored["email"], restored["deleted_at"]) == (email, None)
    assert account_back["deletion_scheduled_for"] is None
    assert account_back["deletion_contact_enc"] is None


async def test_without_the_email_nothing_changes(
    database: Database, request: pytest.FixtureRequest
) -> None:
    email = f"{uuid7()}@example.com"
    with client_with(database, request, FailingMailer()) as client:
        register(client, email)
        deleted = send(client, "POST", DELETION)
        me = client.get("/api/app/me")
        user_id = await user_id_of(database, email)
        account = await account_of(database, user_id)

    assert deleted.status_code == 503
    assert me.status_code == 200
    assert account["deletion_scheduled_for"] is None


async def test_an_address_that_bounced_can_still_delete_its_account(
    database: Database, request: pytest.FixtureRequest
) -> None:
    email = f"{uuid7()}@example.com"
    mailer = RecordingMailer()
    with client_with(database, request, mailer) as client:
        register(client, email)
        user_id = await user_id_of(database, email)
        await owner_row(
            database,
            "INSERT INTO email_suppressions (email_hash, reason, created_at)"
            " VALUES ($1, 'bounce', $2)",
            email_hash(TEST_EMAIL_HASH_KEY, email),
            NOW,
        )
        mailer.sent.clear()
        deleted = send(client, "POST", DELETION)
        account = await account_of(database, user_id)

    assert deleted.status_code == 200
    assert account["deletion_scheduled_for"] == date(2026, 11, 26)
    assert mailer.sent == []


async def test_a_taken_email_stops_the_cancellation_and_keeps_the_link(
    database: Database, request: pytest.FixtureRequest
) -> None:
    email = f"{uuid7()}@example.com"
    mailer = RecordingMailer()
    with client_with(database, request, mailer) as client:
        register(client, email)
        user_id = await user_id_of(database, email)
        mailer.sent.clear()
        send(client, "POST", DELETION)
        token = token_in(mailer.sent[0])
        await owner_row(
            database,
            "INSERT INTO users (id, email, password_hash, created_at) VALUES ($1, $2, 'x', $3)",
            uuid7(),
            email,
            NOW,
        )
        taken = client.post(CANCELLATION, json={"token": token})
        account = await account_of(database, user_id)
        unused = await owner_row(
            database,
            "SELECT used_at FROM email_tokens WHERE user_id = $1 AND purpose = 'cancel_deletion'",
            user_id,
        )

    assert (taken.status_code, taken.json()["detail"]) == (409, "email_taken")
    assert account["deletion_scheduled_for"] == date(2026, 11, 26)
    assert unused["used_at"] is None


async def test_the_link_expires_when_the_purge_comes(
    database: Database, request: pytest.FixtureRequest
) -> None:
    email = f"{uuid7()}@example.com"
    mailer = RecordingMailer()
    clock = FixedClock(NOW)
    with client_with(database, request, mailer, clock) as client:
        register(client, email)
        mailer.sent.clear()
        send(client, "POST", DELETION)
        clock.advance(timedelta(days=30, minutes=1))
        late = client.post(CANCELLATION, json={"token": token_in(mailer.sent[0])})

    assert late.status_code == 400


async def test_a_blocked_account_can_ask_for_its_deletion(
    database: Database, request: pytest.FixtureRequest
) -> None:
    clock = FixedClock(NOW)
    with client_with(database, request, RecordingMailer(), clock) as client:
        register(client)
        clock.advance(timedelta(minutes=1))
        send(client, "POST", "/api/app/legal/consent-withdrawal")
        deleted = send(client, "POST", DELETION)

    assert deleted.status_code == 200
