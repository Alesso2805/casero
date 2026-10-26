import asyncpg
import pytest

from casero.worker import acquire_worker_lock
from database import Database

pytestmark = pytest.mark.anyio


async def test_only_one_worker_holds_the_lock(database: Database) -> None:
    first = await asyncpg.connect(database.dsn("casero_worker"))
    second = await asyncpg.connect(database.dsn("casero_worker"))
    try:
        assert await acquire_worker_lock(first)
        assert not await acquire_worker_lock(second)

        await first.close()

        assert await acquire_worker_lock(second)
    finally:
        await first.close()
        await second.close()
