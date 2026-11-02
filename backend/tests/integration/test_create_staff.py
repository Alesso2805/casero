from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import uuid7

import asyncpg
import pyotp
import pytest

from api_client import TEST_FIELD_CIPHER, FixedClock
from casero.admin.application.staff import StaffEnrollment
from casero.admin.domain.staff import RECOVERY_CODE_COUNT
from casero.admin.infrastructure.staff import HashedRecoveryCodes, totp_secret_context
from casero.identity.infrastructure.passwords import Argon2PasswordHasher
from casero.worker import create_staff
from database import Database

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 11, 1, 15, 0, tzinfo=UTC)
PASSWORD = "una-clave-larga-de-personal"


@pytest.fixture
async def owner(database: Database) -> AsyncIterator[asyncpg.Connection]:
    connection = await asyncpg.connect(database.dsn("casero_owner"))
    try:
        yield connection
    finally:
        await connection.close()


async def create(database: Database, email: str, password: str = PASSWORD) -> object:
    url = database.dsn("casero_owner").replace("postgresql://", "postgresql+asyncpg://", 1)
    return await create_staff(url, TEST_FIELD_CIPHER, FixedClock(NOW), email, password)


async def staff_named(owner: asyncpg.Connection, email: str) -> asyncpg.Record | None:
    return await owner.fetchrow("SELECT * FROM staff_users WHERE lower(email) = lower($1)", email)


async def test_a_new_staff_user_keeps_only_a_hash_and_an_encrypted_secret(
    database: Database, owner: asyncpg.Connection
) -> None:
    email = f"{uuid7()}@example.com"

    enrollment = await create(database, email)

    assert isinstance(enrollment, StaffEnrollment)
    staff = await staff_named(owner, email)
    assert staff is not None
    assert await Argon2PasswordHasher().verify(staff["password_hash"], PASSWORD)
    secret = pyotp.parse_uri(enrollment.totp_uri).secret
    assert secret not in staff["totp_secret_enc"]
    assert staff["totp_secret_enc"].startswith("v1:test:")
    assert (
        TEST_FIELD_CIPHER.decrypt(staff["totp_secret_enc"], totp_secret_context(staff["id"]))
        == secret
    )
    codes = enrollment.recovery_codes
    assert len(set(codes)) == RECOVERY_CODE_COUNT
    assert staff["recovery_codes_hash"] == [HashedRecoveryCodes().hash(code) for code in codes]
    assert not set(codes) & set(staff["recovery_codes_hash"])
    assert staff["created_at"] == NOW


async def test_the_enrollment_link_names_the_person_and_the_product(database: Database) -> None:
    email = f"{uuid7()}@example.com"

    enrollment = await create(database, email)

    assert isinstance(enrollment, StaffEnrollment)
    totp = pyotp.parse_uri(enrollment.totp_uri)
    assert (totp.name, totp.issuer) == (email, "Casero")


async def test_creating_staff_leaves_a_trace_with_no_personal_data(
    database: Database, owner: asyncpg.Connection
) -> None:
    email = f"{uuid7()}@example.com"

    await create(database, email)

    staff = await staff_named(owner, email)
    assert staff is not None
    action = await owner.fetchrow(
        "SELECT staff_user_id, actor, action, entity, at FROM staff_audit_log WHERE entity_id = $1",
        staff["id"],
    )
    assert action is not None
    assert dict(action) == {
        "staff_user_id": None,
        "actor": "cli",
        "action": "staff.create",
        "entity": "staff_users",
        "at": NOW,
    }


async def test_an_email_is_one_staff_user_whatever_its_case(
    database: Database, owner: asyncpg.Connection
) -> None:
    email = f"{uuid7()}@example.com"
    await create(database, email)
    first = await staff_named(owner, email)

    repeated = await create(database, email.upper())

    assert repeated == "email_taken"
    assert await staff_named(owner, email) == first
    assert first is not None
    actions = await owner.fetchval(
        "SELECT count(*) FROM staff_audit_log WHERE action = 'staff.create' AND entity_id = $1",
        first["id"],
    )
    assert actions == 1


async def test_a_short_password_creates_nothing(
    database: Database, owner: asyncpg.Connection
) -> None:
    email = f"{uuid7()}@example.com"

    outcome = await create(database, email, "corta")

    assert outcome == "weak_password"
    assert await staff_named(owner, email) is None


async def test_the_panel_role_cannot_create_staff(database: Database) -> None:
    url = database.dsn("casero_admin").replace("postgresql://", "postgresql+asyncpg://", 1)

    with pytest.raises(Exception, match="permission denied for table staff_users"):
        await create_staff(
            url, TEST_FIELD_CIPHER, FixedClock(NOW), f"{uuid7()}@example.com", PASSWORD
        )
