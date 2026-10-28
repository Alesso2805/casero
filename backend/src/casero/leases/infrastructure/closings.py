from datetime import date
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

OVERDUE = text(
    "SELECT id, end_date FROM leases WHERE ended_at IS NULL AND end_date < :today ORDER BY id"
)
CLOSE = text("UPDATE leases SET ended_at = :ended_at WHERE id = :id AND ended_at IS NULL")


class SqlLeaseClosings:
    """Reads under RLS: only the leases of the account in context are visible."""

    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def overdue(self, today: date) -> list[tuple[UUID, date]]:
        rows = await self._connection.execute(OVERDUE, {"today": today})
        return [(row.id, row.end_date) for row in rows]

    async def close(self, lease_id: UUID, ended_at: date) -> None:
        await self._connection.execute(CLOSE, {"id": lease_id, "ended_at": ended_at})
