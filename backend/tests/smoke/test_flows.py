import os
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from uuid import uuid7

import asyncpg
import pytest

import seed
from database import Database, rolled_back
from smoke.harness import rows_left

pytestmark = pytest.mark.anyio

TODAY = date(2026, 10, 25)
NOW = datetime(2026, 10, 25, 15, 0, tzinfo=UTC)


@pytest.fixture
async def owner(database: Database) -> AsyncIterator[asyncpg.Connection]:
    connection = await asyncpg.connect(database.dsn("casero_owner"))
    try:
        yield connection
    finally:
        await connection.close()


async def test_tenant_link_opens_only_its_lease(
    database: Database, owner: asyncpg.Connection
) -> None:
    account = await seed.seed_account(owner, lease_count=2)
    lease_id = account.lease_ids[0]

    async with rolled_back(database.dsn("casero_app")) as app:
        resolved = await app.fetchrow(
            "SELECT account_id, lease_id FROM app_resolve_tenant_token($1, $2)",
            account.token_hashes[lease_id],
            TODAY,
        )
        assert resolved is not None
        await seed.set_context(app, resolved["account_id"], "tenant", resolved["lease_id"])

        assert [row["id"] for row in await app.fetch("SELECT id FROM leases")] == [lease_id]
        assert await app.fetchval("SELECT display_name FROM accounts") == "Cuenta de prueba"
        assert await app.fetchval("SELECT count(*) FROM tax_payments") == 0


async def test_purge_leaves_only_the_anonymized_account_and_its_payments(
    database: Database, owner: asyncpg.Connection
) -> None:
    account = await seed.seed_account(owner, lease_count=2)
    await owner.execute(
        "UPDATE accounts SET deletion_requested_at = $2, deletion_scheduled_for = $3,"
        " deletion_contact_enc = 'v1:k1:nonce:ciphertext' WHERE id = $1",
        account.account_id,
        NOW - timedelta(days=30),
        TODAY,
    )
    await owner.execute(
        "INSERT INTO registration_invites (id, email, token_hash, expires_at)"
        " VALUES ($1, $2, $3, $4)",
        uuid7(),
        account.email.upper(),
        os.urandom(32),
        NOW,
    )
    await owner.execute(
        "INSERT INTO sessions (id, user_id, token_hash, created_at, last_seen_at, expires_at)"
        " VALUES ($1, $2, $3, $4, $4, $4)",
        uuid7(),
        account.user_id,
        os.urandom(32),
        NOW,
    )
    await owner.execute(
        "INSERT INTO pending_object_deletions (storage_key, account_id, requested_at, attempts,"
        " done_at) VALUES ($1, $2, $3, 1, $3)",
        f"{account.account_id}/{uuid7()}",
        account.account_id,
        NOW,
    )

    worker = await asyncpg.connect(database.dsn("casero_worker"))
    try:
        due = [
            row[0] for row in await worker.fetch("SELECT app_list_account_ids('purge', $1)", TODAY)
        ]
        assert account.account_id in due
        await worker.execute(
            "SELECT purge_account($1, $2, $3)", account.account_id, TODAY, account.email
        )
    finally:
        await worker.close()

    assert await rows_left(owner, account.account_id) == {
        "accounts": 1,
        "subscription_payments": 1,
    }
    purged = await owner.fetchrow(
        "SELECT display_name, ruc, deletion_contact_enc, purged_at FROM accounts WHERE id = $1",
        account.account_id,
    )
    assert purged is not None
    assert tuple(purged) == (None, None, None, TODAY)
    assert await owner.fetchval("SELECT count(*) FROM users WHERE id = $1", account.user_id) == 0
    invites = "SELECT count(*) FROM registration_invites WHERE lower(email) = lower($1)"
    assert await owner.fetchval(invites, account.email) == 0
