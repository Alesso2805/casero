from datetime import datetime

from sqlalchemy import TextClause, text
from sqlalchemy.ext.asyncio import AsyncEngine

FORGET_WAITLIST = text("DELETE FROM waitlist_entries WHERE created_at < :cutoff")
FORGET_COMPLAINTS = text("DELETE FROM complaints WHERE created_at < :cutoff")


class SqlRetention:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def _delete(self, query: TextClause, cutoff: datetime) -> int:
        async with self._engine.begin() as connection:
            result = await connection.execute(query, {"cutoff": cutoff})
            return result.rowcount

    async def forget_waitlist_before(self, cutoff: datetime) -> int:
        return await self._delete(FORGET_WAITLIST, cutoff)

    async def forget_complaints_before(self, cutoff: datetime) -> int:
        return await self._delete(FORGET_COMPLAINTS, cutoff)
