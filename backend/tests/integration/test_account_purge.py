from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from uuid import UUID, uuid7

import asyncpg
import pytest
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

import seed
from api_client import FixedClock
from casero.accounts.application.purge import PurgeAccount
from casero.accounts.infrastructure.purge import NoObjectStore, SqlPurgeRecords
from casero.shared.infrastructure.database import create_engine
from casero.shared.infrastructure.jobs import DailyAccountJob
from database import Database

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 11, 26, 15, 0, tzinfo=UTC)
TODAY = date(2026, 11, 26)
KEPT_ROWS = {"accounts": 1, "subscription_payments": 1}


class RecordingObjects:
    def __init__(self, fail: bool = False) -> None:
        self.deleted: list[str] = []
        self.fail = fail

    async def delete_all_versions(self, storage_key: str) -> None:
        if self.fail:
            raise OSError("bucket down")
        self.deleted.append(storage_key)


@pytest.fixture
async def owner(database: Database) -> AsyncIterator[asyncpg.Connection]:
    connection = await asyncpg.connect(database.dsn("casero_owner"))
    try:
        yield connection
    finally:
        await connection.close()


@pytest.fixture
async def engine(database: Database) -> AsyncIterator[AsyncEngine]:
    worker = create_engine(
        database.dsn("casero_worker").replace("postgresql://", "postgresql+asyncpg://", 1)
    )
    try:
        yield worker
    finally:
        await worker.dispose()


async def due_account(owner: asyncpg.Connection) -> seed.SeededAccount:
    account = await seed.seed_account(owner, lease_count=1)
    await owner.execute(
        "UPDATE accounts SET deletion_requested_at = $2, deletion_scheduled_for = $3,"
        " deletion_contact_enc = 'v1:k1:nonce:ciphertext' WHERE id = $1",
        account.account_id,
        NOW,
        TODAY,
    )
    return account


def purge_job(engine: AsyncEngine, objects: RecordingObjects | NoObjectStore) -> DailyAccountJob:
    clock = FixedClock(NOW)

    async def work(connection: AsyncConnection, account_id: UUID, today: date) -> None:
        await PurgeAccount(SqlPurgeRecords(connection), objects, clock)(account_id, today)

    return DailyAccountJob(engine, clock, f"purge_accounts_{uuid7()}", work, purpose="purge")


async def rows_left(owner: asyncpg.Connection, account_id: UUID) -> dict[str, int]:
    tables = await owner.fetch(
        "SELECT table_name FROM information_schema.columns"
        " WHERE table_schema = 'public' AND column_name = 'account_id'"
    )
    counts = {
        row["table_name"]: await owner.fetchval(
            f"SELECT count(*) FROM {row['table_name']} WHERE account_id = $1",
            account_id,
        )
        for row in tables
    }
    counts["accounts"] = await owner.fetchval(
        "SELECT count(*) FROM accounts WHERE id = $1", account_id
    )
    return {table: count for table, count in counts.items() if count}


async def test_the_worker_deletes_the_objects_and_then_the_rows(
    owner: asyncpg.Connection, engine: AsyncEngine
) -> None:
    account = await due_account(owner)
    keys = [
        row["storage_key"]
        for row in await owner.fetch(
            "SELECT storage_key FROM files WHERE account_id = $1", account.account_id
        )
    ]
    objects = RecordingObjects()

    await purge_job(engine, objects)()

    assert keys
    assert objects.deleted == keys
    assert await rows_left(owner, account.account_id) == KEPT_ROWS
    assert await owner.fetchval("SELECT count(*) FROM users WHERE id = $1", account.user_id) == 0
    purged = await owner.fetchrow(
        "SELECT display_name, ruc, deletion_contact_enc, purged_at FROM accounts WHERE id = $1",
        account.account_id,
    )
    assert purged is not None
    assert tuple(purged) == (None, None, None, TODAY)


async def test_a_bucket_failure_keeps_every_row_for_the_next_try(
    owner: asyncpg.Connection, engine: AsyncEngine
) -> None:
    account = await due_account(owner)
    before = await rows_left(owner, account.account_id)

    await purge_job(engine, RecordingObjects(fail=True))()

    after = await rows_left(owner, account.account_id)
    assert after.pop("job_runs") == 1
    assert after == before
    await purge_job(engine, RecordingObjects())()
    assert await rows_left(owner, account.account_id) == KEPT_ROWS


async def test_an_account_with_files_is_not_purged_without_an_object_store(
    owner: asyncpg.Connection, engine: AsyncEngine
) -> None:
    account = await due_account(owner)

    await purge_job(engine, NoObjectStore())()

    assert (
        await owner.fetchval("SELECT purged_at FROM accounts WHERE id = $1", account.account_id)
        is None
    )


async def test_an_account_without_files_needs_no_object_store(
    owner: asyncpg.Connection, engine: AsyncEngine
) -> None:
    account = await seed.seed_account(owner, lease_count=0)
    await owner.execute(
        "UPDATE accounts SET deletion_requested_at = $2, deletion_scheduled_for = $3,"
        " deletion_contact_enc = 'v1:k1:nonce:ciphertext' WHERE id = $1",
        account.account_id,
        NOW,
        TODAY,
    )

    await purge_job(engine, NoObjectStore())()

    assert await rows_left(owner, account.account_id) == KEPT_ROWS


async def test_the_database_refuses_a_purge_with_a_file_never_queued(
    database: Database, owner: asyncpg.Connection
) -> None:
    account = await due_account(owner)
    worker = await asyncpg.connect(database.dsn("casero_worker"))
    try:
        with pytest.raises(asyncpg.ObjectNotInPrerequisiteStateError):
            await worker.execute("SELECT purge_account($1, $2)", account.account_id, TODAY)
    finally:
        await worker.close()


async def test_an_account_not_due_stays(owner: asyncpg.Connection, engine: AsyncEngine) -> None:
    account = await seed.seed_account(owner, lease_count=0)
    before = await rows_left(owner, account.account_id)

    await purge_job(engine, RecordingObjects())()

    assert await rows_left(owner, account.account_id) == before
