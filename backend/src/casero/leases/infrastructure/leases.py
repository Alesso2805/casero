from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Row, text
from sqlalchemy.ext.asyncio import AsyncConnection

from casero.leases.domain.leases import Lease, LeaseTerms
from casero.shared.kernel.periods import Period

# The rent of a period is the change with the latest (effective_period, created_at) up to it
# (SPEC, lease_rent_changes); a lease that starts later shows its first rent.
SELECT_LEASES = """
SELECT l.id, l.unit_id, l.renter_id, l.due_day, l.start_date, l.end_date, l.ended_at,
       l.control_from_period, l.tax_treatment,
       (SELECT c.monthly_rent_cents FROM lease_rent_changes c WHERE c.lease_id = l.id
        ORDER BY c.effective_period, c.created_at, c.id LIMIT 1) AS initial_rent_cents,
       (SELECT c.monthly_rent_cents FROM lease_rent_changes c WHERE c.lease_id = l.id
          AND c.effective_period <= GREATEST(:period, l.control_from_period)
        ORDER BY c.effective_period DESC, c.created_at DESC, c.id DESC LIMIT 1)
         AS current_rent_cents
FROM leases l
"""
LEASE = text(SELECT_LEASES + " WHERE l.id = :id")
ALL_LEASES = text(SELECT_LEASES + " ORDER BY l.id")
COUNT_ACTIVE = text("SELECT count(*) FROM leases WHERE ended_at IS NULL")
ACTIVE_ON_UNIT = text(
    "SELECT EXISTS (SELECT 1 FROM leases WHERE unit_id = :unit_id AND ended_at IS NULL)"
)
ADD_LEASE = text(
    "INSERT INTO leases (id, account_id, unit_id, renter_id, due_day, start_date,"
    " control_from_period, end_date, tax_treatment, created_at)"
    " VALUES (:id, :account_id, :unit_id, :renter_id, :due_day, :start_date,"
    " :control_from_period, :end_date, :tax_treatment, :created_at)"
    " ON CONFLICT (id) DO NOTHING RETURNING id"
)
ADD_RENT_CHANGE = text(
    "INSERT INTO lease_rent_changes (id, account_id, lease_id, monthly_rent_cents,"
    " effective_period, created_by, created_at) VALUES (:id, :account_id, :lease_id,"
    " :monthly_rent_cents, :effective_period, :created_by, :created_at)"
)


def lease(row: Row[Any]) -> Lease:
    terms = LeaseTerms(
        unit_id=row.unit_id,
        renter_id=row.renter_id,
        monthly_rent_cents=row.initial_rent_cents,
        due_day=row.due_day,
        start_date=row.start_date,
        end_date=row.end_date,
        control_from=Period.parse(row.control_from_period),
        tax_treatment=row.tax_treatment,
    )
    return Lease(row.id, terms, row.ended_at, row.current_rent_cents)


class SqlLeaseStore:
    """Reads under RLS: only the leases of the account in context are visible."""

    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def get(self, lease_id: UUID, period: Period) -> Lease | None:
        row = (
            await self._connection.execute(LEASE, {"id": lease_id, "period": str(period)})
        ).first()
        return None if row is None else lease(row)

    async def all(self, period: Period) -> list[Lease]:
        rows = await self._connection.execute(ALL_LEASES, {"period": str(period)})
        return [lease(row) for row in rows]

    async def count_active(self) -> int:
        count: int = (await self._connection.execute(COUNT_ACTIVE)).scalar_one()
        return count

    async def active_on_unit(self, unit_id: UUID) -> bool:
        active: bool = (
            await self._connection.execute(ACTIVE_ON_UNIT, {"unit_id": unit_id})
        ).scalar_one()
        return active

    async def add(
        self, account_id: UUID, lease_id: UUID, terms: LeaseTerms, created_at: datetime
    ) -> bool:
        inserted = await self._connection.execute(
            ADD_LEASE,
            {
                "id": lease_id,
                "account_id": account_id,
                "unit_id": terms.unit_id,
                "renter_id": terms.renter_id,
                "due_day": terms.due_day,
                "start_date": terms.start_date,
                "control_from_period": str(terms.control_from),
                "end_date": terms.end_date,
                "tax_treatment": terms.tax_treatment,
                "created_at": created_at,
            },
        )
        return inserted.first() is not None

    async def add_rent_change(
        self,
        account_id: UUID,
        change_id: UUID,
        lease_id: UUID,
        monthly_rent_cents: int,
        effective_period: Period,
        created_by: UUID,
        created_at: datetime,
    ) -> None:
        await self._connection.execute(
            ADD_RENT_CHANGE,
            {
                "id": change_id,
                "account_id": account_id,
                "lease_id": lease_id,
                "monthly_rent_cents": monthly_rent_cents,
                "effective_period": str(effective_period),
                "created_by": created_by,
                "created_at": created_at,
            },
        )
