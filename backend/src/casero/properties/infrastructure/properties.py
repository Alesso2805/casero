from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Row, text
from sqlalchemy.ext.asyncio import AsyncConnection

from casero.properties.domain.properties import (
    Ownership,
    Property,
    PropertyDetails,
    Unit,
    UnitDetails,
)

ANY_PROPERTY = text("SELECT EXISTS (SELECT 1 FROM properties)")
SELECT_PROPERTIES = (
    "SELECT id, name, address_line, district, ownership, autovaluo_cents, rented_share_pct,"
    " archived_at FROM properties"
)
SELECT_UNITS = "SELECT id, property_id, name, kind, archived_at FROM units"
ALL_PROPERTIES = text(SELECT_PROPERTIES + " ORDER BY id")
ALL_UNITS = text(SELECT_UNITS + " ORDER BY id")
LOCK_PROPERTY = text(SELECT_PROPERTIES + " WHERE id = :id FOR UPDATE")
LOCK_UNITS_OF = text(SELECT_UNITS + " WHERE property_id = :property_id ORDER BY id FOR UPDATE")
LOCK_UNIT = text(SELECT_UNITS + " WHERE id = :id FOR UPDATE")
OWNERSHIP = text("SELECT ownership FROM properties WHERE id = :id")
ADD_PROPERTY = text(
    "INSERT INTO properties (id, account_id, name, address_line, district, ownership,"
    " autovaluo_cents, rented_share_pct) VALUES (:id, :account_id, :name, :address_line,"
    " :district, :ownership, :autovaluo_cents, :rented_share_pct)"
)
UPDATE_PROPERTY = text(
    "UPDATE properties SET name = :name, address_line = :address_line, district = :district,"
    " ownership = :ownership, autovaluo_cents = :autovaluo_cents,"
    " rented_share_pct = :rented_share_pct WHERE id = :id"
)
ARCHIVE_PROPERTY = text("UPDATE properties SET archived_at = :at WHERE id = :id")
ARCHIVE_UNITS_OF = text(
    "UPDATE units SET archived_at = :at WHERE property_id = :property_id AND archived_at IS NULL"
)
ADD_UNIT = text(
    "INSERT INTO units (id, account_id, property_id, name, kind)"
    " VALUES (:id, :account_id, :property_id, :name, :kind)"
)
UPDATE_UNIT = text("UPDATE units SET name = :name, kind = :kind WHERE id = :id")
ARCHIVE_UNIT = text("UPDATE units SET archived_at = :at WHERE id = :id")


def property_details(row: Row[Any]) -> PropertyDetails:
    return PropertyDetails(
        name=row.name,
        address_line=row.address_line,
        district=row.district,
        ownership=row.ownership,
        autovaluo_cents=row.autovaluo_cents,
        rented_share_pct=row.rented_share_pct,
    )


def unit(row: Row[Any]) -> Unit:
    return Unit(
        row.id, row.property_id, UnitDetails(row.name, row.kind), row.archived_at is not None
    )


def assemble(row: Row[Any], units: Sequence[Unit]) -> Property:
    return Property(
        row.id,
        property_details(row),
        archived=row.archived_at is not None,
        units=tuple(units),
    )


class SqlPropertyStore:
    """Reads under RLS: only the properties of the account in context are visible."""

    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def any_property(self) -> bool:
        exists: bool = (await self._connection.execute(ANY_PROPERTY)).scalar_one()
        return exists

    async def all(self) -> list[Property]:
        units: dict[UUID, list[Unit]] = {}
        for row in await self._connection.execute(ALL_UNITS):
            units.setdefault(row.property_id, []).append(unit(row))
        rows = await self._connection.execute(ALL_PROPERTIES)
        return [assemble(row, units.get(row.id, [])) for row in rows]

    async def lock(self, property_id: UUID) -> Property | None:
        row = (await self._connection.execute(LOCK_PROPERTY, {"id": property_id})).first()
        if row is None:
            return None
        units = await self._connection.execute(LOCK_UNITS_OF, {"property_id": property_id})
        return assemble(row, [unit(unit_row) for unit_row in units])

    async def add(self, account_id: UUID, property_id: UUID, details: PropertyDetails) -> None:
        await self._connection.execute(
            ADD_PROPERTY, {"id": property_id, "account_id": account_id, **vars(details)}
        )

    async def update(self, property_id: UUID, details: PropertyDetails) -> None:
        await self._connection.execute(UPDATE_PROPERTY, {"id": property_id, **vars(details)})

    async def archive(self, property_id: UUID, at: datetime) -> None:
        await self._connection.execute(ARCHIVE_PROPERTY, {"id": property_id, "at": at})
        await self._connection.execute(ARCHIVE_UNITS_OF, {"property_id": property_id, "at": at})

    async def lock_unit(self, unit_id: UUID) -> Unit | None:
        row = (await self._connection.execute(LOCK_UNIT, {"id": unit_id})).first()
        return None if row is None else unit(row)

    async def ownership_of(self, property_id: UUID) -> Ownership:
        ownership: Ownership = (
            await self._connection.execute(OWNERSHIP, {"id": property_id})
        ).scalar_one()
        return ownership

    async def add_unit(
        self, account_id: UUID, unit_id: UUID, property_id: UUID, details: UnitDetails
    ) -> None:
        await self._connection.execute(
            ADD_UNIT,
            {
                "id": unit_id,
                "account_id": account_id,
                "property_id": property_id,
                "name": details.name,
                "kind": details.kind,
            },
        )

    async def update_unit(self, unit_id: UUID, details: UnitDetails) -> None:
        await self._connection.execute(
            UPDATE_UNIT, {"id": unit_id, "name": details.name, "kind": details.kind}
        )

    async def archive_unit(self, unit_id: UUID, at: datetime) -> None:
        await self._connection.execute(ARCHIVE_UNIT, {"id": unit_id, "at": at})
