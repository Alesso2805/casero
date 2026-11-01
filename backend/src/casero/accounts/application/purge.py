from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol
from uuid import UUID

from casero.shared.kernel.clock import Clock


class ObjectStore(Protocol):
    async def delete_all_versions(self, storage_key: str) -> None: ...


class PurgeRecords(Protocol):
    async def queue_objects(self, account_id: UUID, now: datetime) -> None: ...

    async def pending_objects(self, account_id: UUID) -> list[str]: ...

    async def mark_deleted(self, storage_key: str, now: datetime) -> None: ...

    async def purge(self, account_id: UUID, today: date) -> None: ...


@dataclass(frozen=True)
class PurgeAccount:
    """The purge's two phases: first the objects, then the rows (SPEC, "Eliminación").

    A failed object deletion aborts the account's transaction and the job retries it: deleting
    an object twice is harmless, and purge_account refuses while anything is left.
    """

    records: PurgeRecords
    objects: ObjectStore
    clock: Clock

    async def __call__(self, account_id: UUID, today: date) -> None:
        now = self.clock.now()
        await self.records.queue_objects(account_id, now)
        for storage_key in await self.records.pending_objects(account_id):
            await self.objects.delete_all_versions(storage_key)
            await self.records.mark_deleted(storage_key, now)
        await self.records.purge(account_id, today)
