from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid7

import asyncpg
import pytest
from fastapi.testclient import TestClient

from admin_client import a_staff_user, admin_client, code_at, csrf_headers, log_in
from api_client import FixedClock
from casero.admin.application.staff import StaffEnrollment
from casero.shared.kernel.periods import add_months
from database import Database
from tax_flows import client_for, register

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 11, 1, 15, 0, tzinfo=UTC)
TODAY = "2026-11-01"


@pytest.fixture
async def owner(database: Database) -> AsyncIterator[asyncpg.Connection]:
    connection = await asyncpg.connect(database.dsn("casero_owner"))
    try:
        yield connection
    finally:
        await connection.close()


@contextmanager
def panel_as_staff(
    database: Database, clock: FixedClock, enrollment: StaffEnrollment, email: str
) -> Iterator[TestClient]:
    with admin_client(database, clock) as client:
        assert log_in(client, email, code_at(enrollment, clock.now())) == 204
        yield client


def payment(**overrides: object) -> dict[str, object]:
    return {
        "id": str(uuid7()),
        "amount_cents": 1900,
        "paid_on": TODAY,
        "method": "yape",
        "boleta_number": "EB01-1",
        "months": 1,
        **overrides,
    }


def a_landlord(database: Database, request: pytest.FixtureRequest, clock: FixedClock) -> str:
    email = f"casera.{uuid7()}@example.com"
    with client_for(database, request, clock) as client:
        register(client, email)
    return email


def found(client: TestClient, email: str) -> dict[str, Any]:
    answer = client.get("/api/admin/accounts", params={"email": email})
    assert answer.status_code == 200
    [account] = answer.json()
    result: dict[str, Any] = account
    return result


def record(client: TestClient, account_id: str, body: dict[str, object]) -> int:
    answer = client.post(
        f"/api/admin/accounts/{account_id}/payments", json=body, headers=csrf_headers(client)
    )
    return answer.status_code


async def set_trial_end(owner: asyncpg.Connection, email: str, day: date) -> None:
    await owner.execute(
        "UPDATE subscriptions s SET trial_ends_at = $2, ends_at = $2"
        " FROM account_members m JOIN users u ON u.id = m.user_id"
        " WHERE s.account_id = m.account_id AND u.email = $1",
        email,
        day,
    )


async def test_an_account_is_found_by_part_of_its_email_in_any_case(
    database: Database, request: pytest.FixtureRequest
) -> None:
    clock = FixedClock(NOW)
    email = a_landlord(database, request, clock)
    staff, enrollment = await a_staff_user(database, clock)

    with panel_as_staff(database, clock, enrollment, staff) as client:
        answer = client.get("/api/admin/accounts", params={"email": email[6:20].upper()})

    [account] = answer.json()
    assert account["email"] == email
    assert account["display_name"] == "Casera"
    assert (account["status"], account["plan_code"]) == ("trial", "casero")
    assert account["founder"] is False


async def test_percent_and_underscore_in_a_search_are_only_themselves(
    database: Database, request: pytest.FixtureRequest
) -> None:
    clock = FixedClock(NOW)
    a_landlord(database, request, clock)
    staff, enrollment = await a_staff_user(database, clock)

    with panel_as_staff(database, clock, enrollment, staff) as client:
        wildcard = client.get("/api/admin/accounts", params={"email": "casera%example"})
        any_letter = client.get("/api/admin/accounts", params={"email": "casera_"})

    assert (wildcard.json(), any_letter.json()) == ([], [])


async def test_a_search_needs_at_least_three_letters(database: Database) -> None:
    clock = FixedClock(NOW)
    staff, enrollment = await a_staff_user(database, clock)

    with panel_as_staff(database, clock, enrollment, staff) as client:
        answer = client.get("/api/admin/accounts", params={"email": "ab"})

    assert answer.status_code == 422


async def test_the_panel_needs_a_session_to_show_or_change_anything(database: Database) -> None:
    account = uuid7()

    with admin_client(database) as client:
        listed = client.get("/api/admin/accounts", params={"email": "casera"})
        shown = client.get(f"/api/admin/accounts/{account}")
        paid = record(client, str(account), payment())

    assert (listed.status_code, shown.status_code, paid) == (401, 401, 401)


async def test_a_payment_in_the_trial_keeps_its_days_and_shows_on_the_account(
    database: Database, request: pytest.FixtureRequest
) -> None:
    clock = FixedClock(NOW)
    email = a_landlord(database, request, clock)
    staff, enrollment = await a_staff_user(database, clock)
    body = payment(months=2, boleta_number=" EB01-7 ")

    with panel_as_staff(database, clock, enrollment, staff) as client:
        account = found(client, email)
        trial_end = date.fromisoformat(account["trial_ends_at"])
        status = record(client, account["id"], body)
        detail = client.get(f"/api/admin/accounts/{account['id']}").json()

    assert status == 204
    assert detail["ends_at"] == add_months(trial_end, 2).isoformat()
    assert detail["trial_ends_at"] == account["trial_ends_at"]
    assert detail["payments"] == [
        {
            "id": body["id"],
            "amount_cents": 1900,
            "paid_on": TODAY,
            "method": "yape",
            "boleta_number": "EB01-7",
            "months": 2,
        }
    ]


async def test_a_lapsed_trial_that_pays_in_its_grace_days_stops_being_told_it_ended(
    database: Database, request: pytest.FixtureRequest, owner: asyncpg.Connection
) -> None:
    clock = FixedClock(NOW)
    email = f"casera.{uuid7()}@example.com"
    staff, enrollment = await a_staff_user(database, clock)

    with client_for(database, request, clock) as landlord:
        register(landlord, email)
        await set_trial_end(owner, email, date(2026, 10, 30))
        before = landlord.get("/api/app/account").json()
        with panel_as_staff(database, clock, enrollment, staff) as client:
            assert record(client, found(client, email)["id"], payment()) == 204
        after = landlord.get("/api/app/account").json()

    assert (before["status"], before["grace_until"]) == ("grace", "2026-11-05")
    assert (after["status"], after["grace_until"]) == ("active", None)
    assert after["ends_at"] == "2026-11-30"


async def test_a_payment_long_after_it_lapsed_starts_on_the_day_it_was_paid(
    database: Database, request: pytest.FixtureRequest, owner: asyncpg.Connection
) -> None:
    clock = FixedClock(NOW)
    email = a_landlord(database, request, clock)
    await set_trial_end(owner, email, date(2026, 3, 1))
    staff, enrollment = await a_staff_user(database, clock)

    with panel_as_staff(database, clock, enrollment, staff) as client:
        account = found(client, email)
        record(client, account["id"], payment(paid_on="2026-10-20"))
        detail = client.get(f"/api/admin/accounts/{account['id']}").json()

    assert account["status"] == "free"
    assert (detail["status"], detail["ends_at"]) == ("active", "2026-11-20")


async def test_a_payment_made_in_the_grace_days_counts_as_such_even_if_recorded_after_them(
    database: Database, request: pytest.FixtureRequest, owner: asyncpg.Connection
) -> None:
    clock = FixedClock(NOW)
    email = a_landlord(database, request, clock)
    await set_trial_end(owner, email, date(2026, 10, 20))
    staff, enrollment = await a_staff_user(database, clock)

    with panel_as_staff(database, clock, enrollment, staff) as client:
        account = found(client, email)
        record(client, account["id"], payment(paid_on="2026-10-25"))
        detail = client.get(f"/api/admin/accounts/{account['id']}").json()

    assert account["status"] == "free"
    assert detail["ends_at"] == "2026-11-20"


async def test_a_double_click_extends_once(
    database: Database, request: pytest.FixtureRequest
) -> None:
    clock = FixedClock(NOW)
    email = a_landlord(database, request, clock)
    staff, enrollment = await a_staff_user(database, clock)
    body = payment()

    with panel_as_staff(database, clock, enrollment, staff) as client:
        account_id = found(client, email)["id"]
        first = record(client, account_id, body)
        once = client.get(f"/api/admin/accounts/{account_id}").json()
        second = record(client, account_id, body)
        twice = client.get(f"/api/admin/accounts/{account_id}").json()

    assert (first, second) == (204, 204)
    assert twice["ends_at"] == once["ends_at"]
    assert len(twice["payments"]) == 1


async def test_an_id_already_used_with_other_content_is_refused_without_detail(
    database: Database, request: pytest.FixtureRequest
) -> None:
    clock = FixedClock(NOW)
    email = a_landlord(database, request, clock)
    staff, enrollment = await a_staff_user(database, clock)
    body = payment()

    with panel_as_staff(database, clock, enrollment, staff) as client:
        account_id = found(client, email)["id"]
        record(client, account_id, body)
        before = client.get(f"/api/admin/accounts/{account_id}").json()
        answer = client.post(
            f"/api/admin/accounts/{account_id}/payments",
            json={**body, "months": 12},
            headers=csrf_headers(client),
        )
        after = client.get(f"/api/admin/accounts/{account_id}").json()

    assert (answer.status_code, answer.json()) == (409, {"detail": "Conflict"})
    assert after == before


async def test_a_payment_id_of_another_account_is_a_conflict_and_changes_neither(
    database: Database, request: pytest.FixtureRequest
) -> None:
    clock = FixedClock(NOW)
    first_email = a_landlord(database, request, clock)
    second_email = a_landlord(database, request, clock)
    staff, enrollment = await a_staff_user(database, clock)
    body = payment()

    with panel_as_staff(database, clock, enrollment, staff) as client:
        first = found(client, first_email)["id"]
        second = found(client, second_email)
        record(client, first, body)
        status = record(client, second["id"], body)
        after = client.get(f"/api/admin/accounts/{second['id']}").json()

    assert status == 409
    assert after["ends_at"] == second["ends_at"]
    assert after["payments"] == []


async def test_a_payment_dated_tomorrow_is_refused(
    database: Database, request: pytest.FixtureRequest
) -> None:
    clock = FixedClock(NOW)
    email = a_landlord(database, request, clock)
    staff, enrollment = await a_staff_user(database, clock)

    with panel_as_staff(database, clock, enrollment, staff) as client:
        account_id = found(client, email)["id"]
        answer = client.post(
            f"/api/admin/accounts/{account_id}/payments",
            json=payment(paid_on="2026-11-02"),
            headers=csrf_headers(client),
        )

    assert (answer.status_code, answer.json()) == (422, {"detail": "future_date"})


@pytest.mark.parametrize(
    "bad",
    [
        {"amount_cents": 0},
        {"amount_cents": 19.5},
        {"months": 0},
        {"months": 25},
        {"method": "cash"},
        {"boleta_number": "   "},
    ],
)
async def test_a_payment_with_impossible_values_is_refused(
    database: Database, request: pytest.FixtureRequest, bad: dict[str, object]
) -> None:
    clock = FixedClock(NOW)
    email = a_landlord(database, request, clock)
    staff, enrollment = await a_staff_user(database, clock)

    with panel_as_staff(database, clock, enrollment, staff) as client:
        status = record(client, found(client, email)["id"], payment(**bad))

    assert status == 422


async def test_an_account_being_deleted_takes_no_payment(
    database: Database, request: pytest.FixtureRequest, owner: asyncpg.Connection
) -> None:
    clock = FixedClock(NOW)
    email = a_landlord(database, request, clock)
    staff, enrollment = await a_staff_user(database, clock)

    with panel_as_staff(database, clock, enrollment, staff) as client:
        account_id = found(client, email)["id"]
        await owner.execute(
            "UPDATE accounts SET deletion_requested_at = $2, deletion_scheduled_for = $3"
            " WHERE id = $1",
            UUID(account_id),
            NOW,
            date(2026, 12, 1),
        )
        answer = client.post(
            f"/api/admin/accounts/{account_id}/payments",
            json=payment(),
            headers=csrf_headers(client),
        )
        detail = client.get(f"/api/admin/accounts/{account_id}").json()

    assert (answer.status_code, answer.json()) == (409, {"detail": "account_closing"})
    assert detail["payments"] == []


async def test_an_account_that_does_not_exist_is_a_404(database: Database) -> None:
    clock = FixedClock(NOW)
    staff, enrollment = await a_staff_user(database, clock)

    with panel_as_staff(database, clock, enrollment, staff) as client:
        shown = client.get(f"/api/admin/accounts/{uuid7()}")
        paid = record(client, str(uuid7()), payment())

    assert (shown.status_code, paid) == (404, 404)


async def test_the_audit_says_who_did_what_and_never_what_was_searched(
    database: Database, request: pytest.FixtureRequest, owner: asyncpg.Connection
) -> None:
    clock = FixedClock(NOW)
    email = a_landlord(database, request, clock)
    staff, enrollment = await a_staff_user(database, clock)
    body = payment()

    with panel_as_staff(database, clock, enrollment, staff) as client:
        account_id = found(client, email)["id"]
        client.get(f"/api/admin/accounts/{account_id}")
        record(client, account_id, body)
        record(client, account_id, body)

    staff_id = await owner.fetchval("SELECT id FROM staff_users WHERE email = $1", staff)
    rows = await owner.fetch(
        "SELECT action, actor, entity, entity_id FROM staff_audit_log"
        " WHERE staff_user_id = $1 AND action NOT LIKE 'staff.%' ORDER BY id",
        staff_id,
    )
    assert [tuple(row) for row in rows] == [
        ("account.search", "panel", "accounts", None),
        ("account.view", "panel", "accounts", UUID(account_id)),
        ("subscription.payment", "panel", "subscription_payments", UUID(str(body["id"]))),
    ]
    assert email not in str([dict(row) for row in rows])


async def test_only_this_much_of_an_account_reaches_the_panel(
    database: Database, request: pytest.FixtureRequest
) -> None:
    clock = FixedClock(NOW)
    email = a_landlord(database, request, clock)
    staff, enrollment = await a_staff_user(database, clock)

    with panel_as_staff(database, clock, enrollment, staff) as client:
        account = found(client, email)
        detail = client.get(f"/api/admin/accounts/{account['id']}").json()

    assert set(detail) == {
        "id",
        "email",
        "display_name",
        "created_at",
        "email_verified",
        "deletion_requested_at",
        "purged_at",
        "status",
        "plan_code",
        "trial_ends_at",
        "ends_at",
        "founder",
        "payments",
    }
