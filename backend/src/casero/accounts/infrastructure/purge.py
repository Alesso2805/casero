from datetime import date, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

QUEUE_OBJECTS = text(
    "INSERT INTO pending_object_deletions (storage_key, account_id, requested_at, attempts)"
    " SELECT storage_key, account_id, :now, 0 FROM files"
    " WHERE account_id = :account_id AND purged_at IS NULL ON CONFLICT (storage_key) DO NOTHING"
)
PENDING_OBJECTS = text(
    "SELECT storage_key FROM pending_object_deletions"
    " WHERE account_id = :account_id AND done_at IS NULL ORDER BY storage_key"
)
MARK_DELETED = text(
    "UPDATE pending_object_deletions SET done_at = :now, attempts = attempts + 1"
    " WHERE storage_key = :storage_key"
)
PURGE = text("SELECT purge_account(:account_id, :today)")


class SqlPurgeRecords:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def queue_objects(self, account_id: UUID, now: datetime) -> None:
        await self._connection.execute(QUEUE_OBJECTS, {"account_id": account_id, "now": now})

    async def pending_objects(self, account_id: UUID) -> list[str]:
        rows = await self._connection.execute(PENDING_OBJECTS, {"account_id": account_id})
        return [row.storage_key for row in rows]

    async def mark_deleted(self, storage_key: str, now: datetime) -> None:
        await self._connection.execute(MARK_DELETED, {"storage_key": storage_key, "now": now})

    async def purge(self, account_id: UUID, today: date) -> None:
        await self._connection.execute(PURGE, {"account_id": account_id, "today": today})


class NoObjectStore:
    """Nothing is uploaded until CS-19, which brings the real store (BACKLOG).

    Failing keeps an account from being purged with objects left behind.
    """

    async def delete_all_versions(self, storage_key: str) -> None:
        raise RuntimeError("Object deletion arrives with CS-19")
