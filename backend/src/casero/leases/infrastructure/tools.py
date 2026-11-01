from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from casero.leases.domain.tools import LeaseTools

ACTIVE = text(
    "SELECT id, created_at, tools_enabled FROM leases WHERE ended_at IS NULL"
    " ORDER BY created_at, id FOR UPDATE"
)
SET_ENABLED = text("UPDATE leases SET tools_enabled = :enabled WHERE id = ANY(:lease_ids)")


class SqlLeaseTools:
    """Reads under RLS, and locks the rows so a choice and the daily job can't cross."""

    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def active(self) -> list[LeaseTools]:
        rows = await self._connection.execute(ACTIVE)
        return [LeaseTools(row.id, row.created_at, row.tools_enabled) for row in rows]

    async def set_enabled(self, lease_ids: Sequence[UUID], enabled: bool) -> None:
        await self._connection.execute(
            SET_ENABLED, {"lease_ids": list(lease_ids), "enabled": enabled}
        )
