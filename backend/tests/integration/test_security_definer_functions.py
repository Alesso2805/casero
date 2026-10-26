import os
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid7

import asyncpg
import pytest

import seed
from database import Database, rolled_back

pytestmark = pytest.mark.anyio

TODAY = date(2026, 10, 25)
NOW = datetime(2026, 10, 25, 15, 0, tzinfo=UTC)

LEDGER_TABLES = (
    "charges",
    "charge_voids",
    "payments",
    "payment_voids",
    "deposits",
    "deposit_voids",
    "deposit_movements",
    "deposit_movement_voids",
    "lease_rent_changes",
    "tax_payments",
    "tax_payment_voids",
    "legal_acceptances",
    "legal_withdrawals",
    "reminder_logs",
    "audit_log",
    "staff_audit_log",
)


@pytest.fixture
async def owner(database: Database) -> AsyncIterator[asyncpg.Connection]:
    connection = await asyncpg.connect(database.dsn("casero_owner"))
    try:
        yield connection
    finally:
        await connection.close()


@pytest.fixture
async def account(owner: asyncpg.Connection) -> seed.SeededAccount:
    return await seed.seed_account(owner, lease_count=1)


async def resolve(connection: asyncpg.Connection, token_hash: bytes) -> list[tuple[UUID, UUID]]:
    rows = await connection.fetch(
        "SELECT account_id, lease_id FROM app_resolve_tenant_token($1, $2)", token_hash, TODAY
    )
    return [(row["account_id"], row["lease_id"]) for row in rows]


async def schedule_deletion(owner: asyncpg.Connection, account_id: UUID, on: date) -> None:
    await owner.execute(
        "UPDATE accounts SET deletion_requested_at = $2, deletion_scheduled_for = $3,"
        " deletion_contact_enc = 'v1:k1:nonce:ciphertext' WHERE id = $1",
        account_id,
        NOW,
        on,
    )


async def test_resolve_tenant_token_works_without_an_account_context(
    database: Database, account: seed.SeededAccount
) -> None:
    lease_id = account.lease_ids[0]
    async with rolled_back(database.dsn("casero_app")) as app:
        assert await resolve(app, account.token_hashes[lease_id]) == [
            (account.account_id, lease_id)
        ]


@pytest.mark.parametrize(
    ("change", "resolves"),
    [
        ("UPDATE tenant_links SET revoked_at = '2026-10-01' WHERE lease_id = $1", False),
        ("UPDATE leases SET ended_at = '2026-07-27' WHERE id = $1", True),
        ("UPDATE leases SET ended_at = '2026-07-26' WHERE id = $1", False),
    ],
)
async def test_resolve_tenant_token_honours_revocation_and_the_90_day_window(
    database: Database,
    owner: asyncpg.Connection,
    account: seed.SeededAccount,
    change: str,
    resolves: bool,
) -> None:
    lease_id = account.lease_ids[0]
    await owner.execute(change, lease_id)

    async with rolled_back(database.dsn("casero_app")) as app:
        assert bool(await resolve(app, account.token_hashes[lease_id])) is resolves


async def test_resolve_tenant_token_ignores_accounts_being_deleted(
    database: Database, owner: asyncpg.Connection, account: seed.SeededAccount
) -> None:
    await schedule_deletion(owner, account.account_id, TODAY + timedelta(days=30))

    async with rolled_back(database.dsn("casero_app")) as app:
        assert await resolve(app, account.token_hashes[account.lease_ids[0]]) == []


async def test_list_account_ids_separates_jobs_from_due_purges(
    database: Database, owner: asyncpg.Connection
) -> None:
    active = await seed.seed_account(owner, lease_count=0)
    due = await seed.seed_account(owner, lease_count=0)
    later = await seed.seed_account(owner, lease_count=0)
    await schedule_deletion(owner, due.account_id, TODAY)
    await schedule_deletion(owner, later.account_id, TODAY + timedelta(days=1))

    async with rolled_back(database.dsn("casero_worker")) as worker:
        jobs = {
            row[0] for row in await worker.fetch("SELECT app_list_account_ids('jobs', $1)", TODAY)
        }
        purge = {
            row[0] for row in await worker.fetch("SELECT app_list_account_ids('purge', $1)", TODAY)
        }

    assert active.account_id in jobs
    assert due.account_id not in jobs
    assert later.account_id not in jobs
    assert due.account_id in purge
    assert active.account_id not in purge
    assert later.account_id not in purge


async def test_list_account_ids_rejects_unknown_purposes(database: Database) -> None:
    async with rolled_back(database.dsn("casero_worker")) as worker:
        with pytest.raises(asyncpg.InvalidParameterValueError):
            await worker.fetch("SELECT app_list_account_ids('everything', $1)", TODAY)


async def test_cancel_deletion_returns_the_contact_once(
    database: Database, owner: asyncpg.Connection, account: seed.SeededAccount
) -> None:
    await schedule_deletion(owner, account.account_id, TODAY + timedelta(days=30))
    token_hash = os.urandom(32)
    await owner.execute(
        "INSERT INTO email_tokens (id, user_id, purpose, token_hash, expires_at)"
        " VALUES ($1, $2, 'cancel_deletion', $3, $4)",
        uuid7(),
        account.user_id,
        token_hash,
        NOW + timedelta(days=30),
    )
    app = await asyncpg.connect(database.dsn("casero_app"))
    try:
        query = "SELECT * FROM app_cancel_deletion($1, $2)"
        first = [tuple(row) for row in await app.fetch(query, token_hash, NOW)]
        second = await app.fetch(query, token_hash, NOW)
    finally:
        await app.close()

    assert first == [(account.account_id, account.user_id, "v1:k1:nonce:ciphertext")]
    assert second == []
    restored = await owner.fetchrow(
        "SELECT deletion_requested_at, deletion_scheduled_for, deletion_contact_enc"
        " FROM accounts WHERE id = $1",
        account.account_id,
    )
    assert restored is not None
    assert tuple(restored) == (None, None, None)


async def test_cancel_deletion_ignores_expired_tokens(
    database: Database, owner: asyncpg.Connection, account: seed.SeededAccount
) -> None:
    await schedule_deletion(owner, account.account_id, TODAY + timedelta(days=30))
    token_hash = os.urandom(32)
    await owner.execute(
        "INSERT INTO email_tokens (id, user_id, purpose, token_hash, expires_at)"
        " VALUES ($1, $2, 'cancel_deletion', $3, $4)",
        uuid7(),
        account.user_id,
        token_hash,
        NOW - timedelta(seconds=1),
    )

    async with rolled_back(database.dsn("casero_app")) as app:
        assert await app.fetch("SELECT * FROM app_cancel_deletion($1, $2)", token_hash, NOW) == []


async def test_purge_refuses_an_account_that_is_not_due(
    database: Database, owner: asyncpg.Connection, account: seed.SeededAccount
) -> None:
    await schedule_deletion(owner, account.account_id, TODAY + timedelta(days=1))

    async with rolled_back(database.dsn("casero_worker")) as worker:
        with pytest.raises(asyncpg.ObjectNotInPrerequisiteStateError):
            await worker.execute(
                "SELECT purge_account($1, $2, $3)", account.account_id, TODAY, account.email
            )


async def test_purge_refuses_while_storage_objects_are_pending(
    database: Database, owner: asyncpg.Connection, account: seed.SeededAccount
) -> None:
    await schedule_deletion(owner, account.account_id, TODAY)
    await owner.execute(
        "INSERT INTO pending_object_deletions (storage_key, account_id, requested_at, attempts)"
        " VALUES ($1, $2, $3, 0)",
        f"{account.account_id}/{uuid7()}",
        account.account_id,
        NOW,
    )

    async with rolled_back(database.dsn("casero_worker")) as worker:
        with pytest.raises(asyncpg.ObjectNotInPrerequisiteStateError):
            await worker.execute(
                "SELECT purge_account($1, $2, $3)", account.account_id, TODAY, account.email
            )


@pytest.mark.parametrize("role", ["casero_app", "casero_worker", "casero_admin"])
async def test_ledger_tables_reject_update_and_delete(database: Database, role: str) -> None:
    connection = await asyncpg.connect(database.dsn(role))
    try:
        for table in LEDGER_TABLES:
            column = "reason" if table.endswith("_voids") else "id"
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await connection.execute(f"UPDATE {table} SET {column} = {column} WHERE false")
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await connection.execute(f"DELETE FROM {table} WHERE false")
    finally:
        await connection.close()


@pytest.mark.parametrize(
    ("role", "call"),
    [
        ("casero_app", "SELECT app_list_account_ids('jobs', '2026-10-25')"),
        ("casero_app", "SELECT purge_account(gen_random_uuid(), '2026-10-25', 'x@example.test')"),
        ("casero_admin", "SELECT purge_account(gen_random_uuid(), '2026-10-25', 'x@example.test')"),
        (
            "casero_worker",
            "SELECT * FROM app_resolve_tenant_token(gen_random_uuid()::text::bytea, '2026-10-25')",
        ),
    ],
)
async def test_functions_are_executable_only_by_their_role(
    database: Database, role: str, call: str
) -> None:
    async with rolled_back(database.dsn(role)) as connection:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await connection.execute(call)
