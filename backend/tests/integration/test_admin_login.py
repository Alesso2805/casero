from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid7

import asyncpg
import pyotp
import pytest
from fastapi.testclient import TestClient

from admin_client import admin_client
from api_client import TEST_FIELD_CIPHER, FixedClock
from casero.admin.application.staff import StaffEnrollment
from casero.shared.infrastructure.csrf import CSRF_COOKIE, CSRF_HEADER
from casero.worker import create_staff
from database import Database

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 11, 1, 15, 0, tzinfo=UTC)
PASSWORD = "una-clave-larga-de-personal"
STAFF_COOKIE = "__Host-casero_staff"


@pytest.fixture
async def owner(database: Database) -> AsyncIterator[asyncpg.Connection]:
    connection = await asyncpg.connect(database.dsn("casero_owner"))
    try:
        yield connection
    finally:
        await connection.close()


async def a_staff_user(database: Database, clock: FixedClock) -> tuple[str, StaffEnrollment]:
    email = f"{uuid7()}@example.com"
    url = database.dsn("casero_owner").replace("postgresql://", "postgresql+asyncpg://", 1)
    enrollment = await create_staff(url, TEST_FIELD_CIPHER, clock, email, PASSWORD)
    assert isinstance(enrollment, StaffEnrollment)
    return email, enrollment


def csrf_headers(client: TestClient) -> dict[str, str]:
    client.get("/api/admin/csrf")
    return {CSRF_HEADER: client.cookies[CSRF_COOKIE]}


def code_at(enrollment: StaffEnrollment, moment: datetime) -> str:
    totp = pyotp.parse_uri(enrollment.totp_uri)
    assert isinstance(totp, pyotp.TOTP)
    return totp.at(moment)


def log_in(client: TestClient, email: str, code: str, password: str = PASSWORD) -> int:
    answer = client.post(
        "/api/admin/session",
        json={"email": email, "password": password, "code": code},
        headers=csrf_headers(client),
    )
    return answer.status_code


def wear_token(client: TestClient, token: str) -> None:
    """Clears the jar first: a second cookie of the same name would be sent alongside the first."""
    client.cookies.clear()
    client.cookies.set(STAFF_COOKIE, token)


def signed_in(client: TestClient) -> int:
    return client.get("/api/admin/me").status_code


async def staff_id_of(owner: asyncpg.Connection, email: str) -> UUID:
    staff_id: UUID = await owner.fetchval("SELECT id FROM staff_users WHERE email = $1", email)
    return staff_id


async def actions_of(owner: asyncpg.Connection, staff_id: UUID) -> list[tuple[str, str]]:
    rows = await owner.fetch(
        "SELECT action, actor FROM staff_audit_log WHERE staff_user_id = $1 ORDER BY id", staff_id
    )
    return [(row["action"], row["actor"]) for row in rows]


async def test_the_password_and_a_code_open_a_session_kept_only_as_a_hash(
    database: Database, owner: asyncpg.Connection
) -> None:
    clock = FixedClock(NOW)
    email, enrollment = await a_staff_user(database, clock)

    with admin_client(database, clock) as client:
        status = log_in(client, email, code_at(enrollment, NOW))
        token = client.cookies[STAFF_COOKIE]
        me = client.get("/api/admin/me")

    assert status == 204
    assert (me.status_code, me.json()) == (200, {"email": email})
    staff_id = await staff_id_of(owner, email)
    session = await owner.fetchrow(
        "SELECT token_hash, created_at, expires_at FROM staff_sessions WHERE staff_user_id = $1",
        staff_id,
    )
    assert session is not None
    assert token.encode() != bytes(session["token_hash"])
    assert session["expires_at"] - session["created_at"] == timedelta(hours=8)
    assert await actions_of(owner, staff_id) == [("staff.login", "panel")]


async def test_the_session_cookie_is_host_only_strict_and_out_of_reach_of_scripts(
    database: Database,
) -> None:
    clock = FixedClock(NOW)
    email, enrollment = await a_staff_user(database, clock)

    with admin_client(database, clock) as client:
        answer = client.post(
            "/api/admin/session",
            json={"email": email, "password": PASSWORD, "code": code_at(enrollment, NOW)},
            headers=csrf_headers(client),
        )

    cookie = next(
        header
        for header in answer.headers.get_list("set-cookie")
        if header.startswith(STAFF_COOKIE)
    )
    attributes = {part.strip().lower() for part in cookie.split(";")[1:]}
    assert attributes >= {"httponly", "secure", "samesite=strict", "path=/", "max-age=28800"}
    assert not any(attribute.startswith("domain") for attribute in attributes)


async def test_each_wrong_factor_gets_the_same_answer_and_opens_nothing(
    database: Database, owner: asyncpg.Connection
) -> None:
    clock = FixedClock(NOW)
    email, enrollment = await a_staff_user(database, clock)
    right_code = code_at(enrollment, NOW)

    with admin_client(database, clock) as client:
        wrong_password = log_in(client, email, right_code, "otra-clave-larga-de-personal")
        wrong_code = log_in(client, email, "000000" if right_code != "000000" else "111111")
        unknown_email = log_in(client, f"{uuid7()}@example.com", right_code)
        after_all = signed_in(client)

    assert (wrong_password, wrong_code, unknown_email) == (401, 401, 401)
    assert after_all == 401
    staff_id = await staff_id_of(owner, email)
    assert (
        await owner.fetchval(
            "SELECT count(*) FROM staff_sessions WHERE staff_user_id = $1", staff_id
        )
        == 0
    )
    assert await actions_of(owner, staff_id) == [
        ("staff.login_failed", "panel"),
        ("staff.login_failed", "panel"),
    ]


async def test_a_code_from_the_step_before_works_and_one_from_two_steps_before_does_not(
    database: Database,
) -> None:
    clock = FixedClock(NOW)
    email, enrollment = await a_staff_user(database, clock)

    with admin_client(database, clock) as client:
        too_old = log_in(client, email, code_at(enrollment, NOW - timedelta(seconds=60)))
        just_old = log_in(client, email, code_at(enrollment, NOW - timedelta(seconds=30)))

    assert (too_old, just_old) == (401, 204)


async def test_a_recovery_code_works_once_and_stands_in_for_the_app(
    database: Database, owner: asyncpg.Connection
) -> None:
    clock = FixedClock(NOW)
    email, enrollment = await a_staff_user(database, clock)
    code = enrollment.recovery_codes[0]

    with admin_client(database, clock) as client:
        first = log_in(client, email, code)
        second = log_in(client, email, code)
        another = log_in(client, email, f"  {enrollment.recovery_codes[1].upper()} ")

    assert (first, second, another) == (204, 401, 204)
    left = await owner.fetchval(
        "SELECT cardinality(recovery_codes_hash) FROM staff_users WHERE email = $1", email
    )
    assert left == len(enrollment.recovery_codes) - 2
    actions = await actions_of(owner, await staff_id_of(owner, email))
    assert actions == [
        ("staff.login_recovery_code", "panel"),
        ("staff.login_failed", "panel"),
        ("staff.login_recovery_code", "panel"),
    ]


async def test_a_wrong_password_does_not_spend_a_recovery_code(
    database: Database, owner: asyncpg.Connection
) -> None:
    clock = FixedClock(NOW)
    email, enrollment = await a_staff_user(database, clock)

    with admin_client(database, clock) as client:
        status = log_in(client, email, enrollment.recovery_codes[0], "otra-clave-larga-de-personal")

    assert status == 401
    left = await owner.fetchval(
        "SELECT cardinality(recovery_codes_hash) FROM staff_users WHERE email = $1", email
    )
    assert left == len(enrollment.recovery_codes)


async def test_a_session_ends_after_30_minutes_idle(database: Database) -> None:
    clock = FixedClock(NOW)
    email, enrollment = await a_staff_user(database, clock)

    with admin_client(database, clock) as client:
        log_in(client, email, code_at(enrollment, NOW))
        clock.advance(timedelta(minutes=29, seconds=59))
        before_the_limit = signed_in(client)
        clock.advance(timedelta(minutes=30))
        at_the_limit = signed_in(client)

    assert (before_the_limit, at_the_limit) == (200, 401)


async def test_a_session_ends_at_8_hours_however_much_it_is_used(database: Database) -> None:
    clock = FixedClock(NOW)
    email, enrollment = await a_staff_user(database, clock)

    with admin_client(database, clock) as client:
        log_in(client, email, code_at(enrollment, NOW))
        statuses = []
        for _ in range(16):
            clock.advance(timedelta(minutes=30) - timedelta(seconds=1))
            statuses.append(signed_in(client))
        clock.advance(timedelta(minutes=9))
        after_8_hours = signed_in(client)

    assert set(statuses) == {200}
    assert after_8_hours == 401


async def test_logging_out_ends_the_session_and_leaves_a_trace(
    database: Database, owner: asyncpg.Connection
) -> None:
    clock = FixedClock(NOW)
    email, enrollment = await a_staff_user(database, clock)

    with admin_client(database, clock) as client:
        log_in(client, email, code_at(enrollment, NOW))
        token = client.cookies[STAFF_COOKIE]
        answer = client.delete("/api/admin/session", headers=csrf_headers(client))
        after_logout = signed_in(client)
        wear_token(client, token)
        with_the_old_token = signed_in(client)

    assert answer.status_code == 204
    assert (after_logout, with_the_old_token) == (401, 401)
    assert await actions_of(owner, await staff_id_of(owner, email)) == [
        ("staff.login", "panel"),
        ("staff.logout", "panel"),
    ]


async def test_a_new_login_closes_the_earlier_session(database: Database) -> None:
    clock = FixedClock(NOW)
    email, enrollment = await a_staff_user(database, clock)

    with admin_client(database, clock) as client:
        log_in(client, email, code_at(enrollment, NOW))
        earlier = client.cookies[STAFF_COOKIE]
        log_in(client, email, code_at(enrollment, NOW))
        latest = client.cookies[STAFF_COOKIE]
        with_the_latest = signed_in(client)
        wear_token(client, earlier)
        with_the_earlier = signed_in(client)

    assert earlier != latest
    assert (with_the_latest, with_the_earlier) == (200, 401)


async def test_disabling_a_staff_user_ends_their_session_and_their_login(
    database: Database, owner: asyncpg.Connection
) -> None:
    clock = FixedClock(NOW)
    email, enrollment = await a_staff_user(database, clock)

    with admin_client(database, clock) as client:
        log_in(client, email, code_at(enrollment, NOW))
        await owner.execute("UPDATE staff_users SET disabled_at = $1 WHERE email = $2", NOW, email)
        session = signed_in(client)
        login = log_in(client, email, code_at(enrollment, NOW))

    assert (session, login) == (401, 401)


async def test_logging_in_and_out_need_the_csrf_token(database: Database) -> None:
    clock = FixedClock(NOW)
    email, enrollment = await a_staff_user(database, clock)
    body = {"email": email, "password": PASSWORD, "code": code_at(enrollment, NOW)}

    with admin_client(database, clock) as client:
        login = client.post("/api/admin/session", json=body)
        log_in(client, email, code_at(enrollment, NOW))
        logout = client.delete("/api/admin/session", headers={CSRF_HEADER: "wrong"})
        still_in = signed_in(client)

    assert (login.status_code, logout.status_code, still_in) == (403, 403, 200)


async def test_without_a_session_the_panel_says_only_that(database: Database) -> None:
    with admin_client(database) as client:
        answer = client.get("/api/admin/me")

    assert (answer.status_code, answer.json()) == (401, {"detail": "no_session"})
