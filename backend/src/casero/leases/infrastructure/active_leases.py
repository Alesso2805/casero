from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

ON_UNIT = text("SELECT EXISTS (SELECT 1 FROM leases WHERE unit_id = :unit_id AND ended_at IS NULL)")
ON_PROPERTY = text(
    "SELECT EXISTS (SELECT 1 FROM leases l"
    " JOIN units u ON u.account_id = l.account_id AND u.id = l.unit_id"
    " WHERE u.property_id = :property_id AND l.ended_at IS NULL)"
)


class SqlActiveLeases:
    """Reads under RLS: only the leases of the account in context are visible."""

    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def on_unit(self, unit_id: UUID) -> bool:
        active: bool = (await self._connection.execute(ON_UNIT, {"unit_id": unit_id})).scalar_one()
        return active

    async def on_property(self, property_id: UUID) -> bool:
        result = await self._connection.execute(ON_PROPERTY, {"property_id": property_id})
        active: bool = result.scalar_one()
        return active
