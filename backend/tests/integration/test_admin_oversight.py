import json
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg
import pytest
from fastapi.testclient import TestClient

from admin_client import a_staff_user, admin_client, code_at, log_in
from api_client import FixedClock, RecordingMailer
from casero.admin.application.staff import StaffEnrollment
from casero.worker import register_complaint, respond_to_complaint
from database import Database

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 11, 2, 15, 0, tzinfo=UTC)
FULL_NAME = "Rosa Quispe"
DOCUMENT = "45678912"
CONSUMER_EMAIL = "rosa@example.com"
DETAIL = "El servicio no funcionó."
SHEET = {
    "full_name": FULL_NAME,
    "document_type": "dni",
    "document_number": DOCUMENT,
    "email": CONSUMER_EMAIL,
    "address": "Av. Ficticia 100",
    "item_kind": "service",
    "kind": "claim",
    "detail": DETAIL,
    "response_channel": "email",
}


@pytest.fixture
async def owner(database: Database) -> AsyncIterator[asyncpg.Connection]:
    connection = await asyncpg.connect(database.dsn("casero_owner"))
    try:
        yield connection
    finally:
        await connection.close()


def url(database: Database, role: str) -> str:
    return database.dsn(role).replace("postgresql://", "postgresql+asyncpg://", 1)


@contextmanager
def panel_as_staff(
    database: Database, clock: FixedClock, enrollment: StaffEnrollment, email: str
) -> Iterator[TestClient]:
    with admin_client(database, clock) as client:
        assert log_in(client, email, code_at(enrollment, clock.now())) == 204
        yield client


async def a_complaint(database: Database, filed_at: datetime) -> str:
    return await register_complaint(
        url(database, "casero_owner"), FixedClock(filed_at), json.dumps(SHEET), filed_at
    )


def deadline_of(client: TestClient, number: str) -> dict[str, Any]:
    [deadline] = [
        row for row in client.get("/api/admin/complaints").json() if row["number"] == number
    ]
    result: dict[str, Any] = deadline
    return result


async def test_the_panel_shows_the_schedule_exactly_as_it_was_loaded(
    database: Database, owner: asyncpg.Connection
) -> None:
    clock = FixedClock(NOW)
    staff, enrollment = await a_staff_user(database, clock)

    with panel_as_staff(database, clock, enrollment, staff) as client:
        answer = client.get("/api/admin/sunat-schedule")

    loaded = await owner.fetch(
        "SELECT period, ruc_group, due_date, source_url FROM sunat_due_dates"
        " ORDER BY period, ruc_group"
    )
    assert loaded
    assert [
        (row["period"], row["ruc_group"], row["due_on"], row["source_url"]) for row in answer.json()
    ] == [
        (row["period"], row["ruc_group"], row["due_date"].isoformat(), row["source_url"])
        for row in loaded
    ]


async def test_a_complaint_shows_its_deadline_and_nothing_of_the_consumer(
    database: Database,
) -> None:
    clock = FixedClock(NOW)
    number = await a_complaint(database, NOW)
    staff, enrollment = await a_staff_user(database, clock)

    with panel_as_staff(database, clock, enrollment, staff) as client:
        answer = client.get("/api/admin/complaints")
        deadline = deadline_of(client, number)

    assert set(deadline) == {
        "number",
        "kind",
        "filed_at",
        "due_on",
        "responded_at",
        "response_channel",
        "state",
    }
    assert (deadline["kind"], deadline["state"]) == ("claim", "open")
    for personal in (FULL_NAME, DOCUMENT, CONSUMER_EMAIL, DETAIL):
        assert personal not in answer.text


async def test_a_complaint_is_open_through_its_last_day_and_overdue_after_it(
    database: Database,
) -> None:
    number = await a_complaint(database, NOW)
    staff_clock = FixedClock(NOW)
    staff, enrollment = await a_staff_user(database, staff_clock)
    with panel_as_staff(database, staff_clock, enrollment, staff) as client:
        due_on = datetime.fromisoformat(deadline_of(client, number)["due_on"])

    last_day = FixedClock(due_on.replace(hour=20, tzinfo=UTC))
    with panel_as_staff(database, last_day, enrollment, staff) as client:
        on_the_last_day = deadline_of(client, number)["state"]

    day_after = FixedClock(due_on.replace(hour=20, tzinfo=UTC) + timedelta(days=1))
    with panel_as_staff(database, day_after, enrollment, staff) as client:
        after_it = deadline_of(client, number)["state"]

    assert (on_the_last_day, after_it) == ("open", "overdue")


async def test_an_answered_complaint_stays_answered_past_its_deadline(database: Database) -> None:
    clock = FixedClock(NOW)
    number = await a_complaint(database, NOW)
    await respond_to_complaint(
        url(database, "casero_admin"),
        RecordingMailer(),
        "reclamos@example.com",
        clock,
        number,
        "Revisamos tu caso.",
        None,
    )
    later = FixedClock(NOW + timedelta(days=60))
    staff, enrollment = await a_staff_user(database, later)

    with panel_as_staff(database, later, enrollment, staff) as client:
        deadline = deadline_of(client, number)

    assert deadline["state"] == "answered"
    assert deadline["responded_at"] is not None


async def test_unanswered_complaints_come_first_with_the_closest_deadline_on_top(
    database: Database,
) -> None:
    clock = FixedClock(NOW)
    answered = await a_complaint(database, NOW - timedelta(days=40))
    await respond_to_complaint(
        url(database, "casero_admin"),
        RecordingMailer(),
        "reclamos@example.com",
        clock,
        answered,
        "Revisamos tu caso.",
        None,
    )
    later = await a_complaint(database, NOW)
    sooner = await a_complaint(database, NOW - timedelta(days=5))
    staff, enrollment = await a_staff_user(database, clock)

    with panel_as_staff(database, clock, enrollment, staff) as client:
        numbers = [row["number"] for row in client.get("/api/admin/complaints").json()]

    assert numbers.index(sooner) < numbers.index(later) < numbers.index(answered)


@pytest.mark.parametrize("path", ["/api/admin/sunat-schedule", "/api/admin/complaints"])
async def test_these_views_need_a_session(database: Database, path: str) -> None:
    with admin_client(database) as client:
        assert client.get(path).status_code == 401


@pytest.mark.parametrize("path", ["/api/admin/sunat-schedule", "/api/admin/complaints"])
async def test_the_panel_can_read_these_and_never_write_them(database: Database, path: str) -> None:
    clock = FixedClock(NOW)
    staff, enrollment = await a_staff_user(database, clock)

    with panel_as_staff(database, clock, enrollment, staff) as client:
        statuses = {
            client.request(method, path).status_code
            for method in ("POST", "PUT", "PATCH", "DELETE")
        }

    assert statuses == {405}


async def test_each_view_leaves_a_row_in_the_audit(
    database: Database, owner: asyncpg.Connection
) -> None:
    clock = FixedClock(NOW)
    staff, enrollment = await a_staff_user(database, clock)

    with panel_as_staff(database, clock, enrollment, staff) as client:
        client.get("/api/admin/sunat-schedule")
        client.get("/api/admin/complaints")

    staff_id = await owner.fetchval("SELECT id FROM staff_users WHERE email = $1", staff)
    rows = await owner.fetch(
        "SELECT action, entity, entity_id FROM staff_audit_log"
        " WHERE staff_user_id = $1 AND action NOT LIKE 'staff.%' ORDER BY id",
        staff_id,
    )
    assert [tuple(row) for row in rows] == [
        ("schedule.view", "sunat_due_dates", None),
        ("complaints.view", "complaints", None),
    ]
