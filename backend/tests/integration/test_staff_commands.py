import json
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid7

import asyncpg
import pytest
from pydantic import ValidationError

from api_client import FixedClock, RecordingMailer, address_for, api_client
from casero.accounts.infrastructure.founders import a_year_after, grant_founder
from casero.shared.kernel.email import Email, MailDeliveryError
from casero.worker import lima_moment, register_complaint, respond_to_complaint
from database import Database
from tax_flows import register

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 27, 15, 0, tzinfo=UTC)
INBOX = "reclamos@example.com"
RESPONSE = "Revisamos tu caso y te devolvimos el pago."
SHEET = {
    "full_name": "Rosa Quispe",
    "document_type": "dni",
    "document_number": "45678912",
    "email": "rosa@example.com",
    "address": "Av. Ficticia 100",
    "item_kind": "service",
    "kind": "claim",
    "detail": "El servicio no funcionó.",
    "response_channel": "email",
}


class FailingMailer:
    async def send(self, email: Email) -> None:
        raise MailDeliveryError("down")


def url(database: Database, role: str) -> str:
    return database.dsn(role).replace("postgresql://", "postgresql+asyncpg://", 1)


@pytest.fixture
async def owner(database: Database) -> AsyncIterator[asyncpg.Connection]:
    connection = await asyncpg.connect(database.dsn("casero_owner"))
    try:
        yield connection
    finally:
        await connection.close()


async def a_complaint(database: Database, **overrides: object) -> str:
    return await register_complaint(
        url(database, "casero_owner"), FixedClock(NOW), json.dumps({**SHEET, **overrides}), NOW
    )


async def complaint_row(owner: asyncpg.Connection, number: str) -> Any:
    return await owner.fetchrow("SELECT * FROM complaints WHERE number = $1", number)


async def actions_on(owner: asyncpg.Connection, entity_id: UUID) -> list[tuple[str, str]]:
    rows = await owner.fetch(
        "SELECT action, actor FROM staff_audit_log WHERE entity_id = $1 ORDER BY at, action",
        entity_id,
    )
    return [(row["action"], row["actor"]) for row in rows]


async def respond(database: Database, mailer: Any, number: str, sent_on: date | None = None) -> str:
    return await respond_to_complaint(
        url(database, "casero_admin"), mailer, INBOX, FixedClock(NOW), number, RESPONSE, sent_on
    )


async def test_an_email_response_goes_out_once_and_is_recorded(
    database: Database, owner: asyncpg.Connection
) -> None:
    number = await a_complaint(database)
    mailer = RecordingMailer()

    first = await respond(database, mailer, number)
    second = await respond(database, mailer, number)

    row = await complaint_row(owner, number)
    assert (first, second) == ("responded", "already_responded")
    assert (row["response"], row["responded_at"]) == (RESPONSE, NOW)
    [sent] = mailer.sent
    assert (sent.to, sent.reply_to, sent.text) == ("rosa@example.com", INBOX, RESPONSE)
    assert sent.subject == f"Respuesta a tu reclamo N.° {number}"
    assert await actions_on(owner, row["id"]) == [
        ("complaint.register", "cli"),
        ("complaint.respond", "cli"),
    ]


async def test_a_failed_email_records_nothing(
    database: Database, owner: asyncpg.Connection
) -> None:
    number = await a_complaint(database)

    outcome = await respond(database, FailingMailer(), number)

    row = await complaint_row(owner, number)
    assert outcome == "email_failed"
    assert row["responded_at"] is None
    assert await actions_on(owner, row["id"]) == [("complaint.register", "cli")]


async def test_a_letter_needs_its_date_and_sends_no_email(
    database: Database, owner: asyncpg.Connection
) -> None:
    number = await a_complaint(database, response_channel="letter")
    mailer = RecordingMailer()

    missing = await respond(database, mailer, number)
    recorded = await respond(database, mailer, number, date(2026, 10, 26))

    row = await complaint_row(owner, number)
    assert (missing, recorded) == ("needs_sent_on", "responded")
    assert row["responded_at"] == datetime(2026, 10, 26, 17, 0, tzinfo=UTC)
    assert mailer.sent == []


async def test_an_unknown_number_changes_nothing(database: Database) -> None:
    assert await respond(database, RecordingMailer(), "000000000-2026") == "not_found"


async def test_a_complaint_received_by_email_keeps_its_original_date(
    database: Database, owner: asyncpg.Connection
) -> None:
    arrived = lima_moment("2025-12-31T22:30")
    clock = FixedClock(NOW)

    number = await register_complaint(
        url(database, "casero_owner"), clock, json.dumps(SHEET), arrived
    )

    row = await complaint_row(owner, number)
    assert number.endswith("-2025")
    assert row["created_at"] == datetime(2026, 1, 1, 3, 30, tzinfo=UTC)
    assert row["due_at"] > date(2026, 1, 15)
    assert row["document_number"] == "45678912"


async def test_a_bad_sheet_is_refused_before_touching_the_database(database: Database) -> None:
    with pytest.raises(ValidationError):
        await register_complaint(
            url(database, "casero_owner"),
            FixedClock(NOW),
            json.dumps({**SHEET, "document_number": "12"}),
            NOW,
        )


def test_a_moment_with_its_own_zone_stays_as_it_is() -> None:
    assert lima_moment("2026-10-27T10:00:00+00:00").tzinfo == timezone(timedelta(0))
    assert lima_moment("2026-10-27T10:00").utcoffset() == timedelta(hours=-5)


async def test_a_founder_gets_a_year_once(
    database: Database, request: pytest.FixtureRequest, owner: asyncpg.Connection
) -> None:
    email = f"{uuid7()}@example.com"
    with api_client(
        database, address_for(request.node.name), FixedClock(NOW), registration_mode="open"
    ) as client:
        register(client, email)
    admin = url(database, "casero_admin")
    today = date(2026, 10, 27)

    granted = await grant_founder(admin, email.upper(), today, NOW)
    again = await grant_founder(admin, email, today, NOW)
    unknown = await grant_founder(admin, f"{uuid7()}@example.com", today, NOW)

    assert granted is not None
    assert (again, unknown) == (None, None)
    row = await owner.fetchrow("SELECT founder, ends_at FROM subscriptions WHERE id = $1", granted)
    assert row is not None
    assert tuple(row) == (True, date(2027, 10, 27))
    assert await actions_on(owner, granted) == [("subscription.grant_founder", "cli")]


def test_a_founders_year_from_a_leap_day_ends_on_the_28th() -> None:
    assert a_year_after(date(2028, 2, 29)) == date(2029, 2, 28)
