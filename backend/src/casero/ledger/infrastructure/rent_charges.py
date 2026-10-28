from collections import defaultdict
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from casero.ledger.domain.charges import LeaseToCharge, RentChange, RentCharge
from casero.shared.kernel.periods import Period

LEASES = text(
    "SELECT id, due_day, start_date, control_from_period, COALESCE(ended_at, end_date) AS ends_on"
    " FROM leases WHERE (CAST(:lease_id AS uuid) IS NULL OR id = :lease_id) ORDER BY id"
)
RENT_CHANGES = text(
    "SELECT id, lease_id, monthly_rent_cents, effective_period, created_at"
    " FROM lease_rent_changes WHERE (CAST(:lease_id AS uuid) IS NULL OR lease_id = :lease_id)"
)
CHARGED = text(
    "SELECT lease_id, period FROM charges WHERE kind = 'rent'"
    " AND (CAST(:lease_id AS uuid) IS NULL OR lease_id = :lease_id)"
)
ADD_RENT = text(
    "INSERT INTO charges (id, account_id, lease_id, kind, period, amount_cents, due_date,"
    " created_at) VALUES (:id, :account_id, :lease_id, 'rent', :period, :amount_cents,"
    " :due_date, :created_at) ON CONFLICT (lease_id, period) WHERE kind = 'rent' DO NOTHING"
)


class SqlRentCharges:
    """Reads under RLS: only the account in context is visible."""

    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def leases_to_charge(self, lease_id: UUID | None) -> list[LeaseToCharge]:
        scope = {"lease_id": lease_id}
        changes: defaultdict[UUID, list[RentChange]] = defaultdict(list)
        for row in await self._connection.execute(RENT_CHANGES, scope):
            changes[row.lease_id].append(
                RentChange(
                    row.id,
                    row.monthly_rent_cents,
                    Period.parse(row.effective_period),
                    row.created_at,
                )
            )
        charged: defaultdict[UUID, set[Period]] = defaultdict(set)
        for row in await self._connection.execute(CHARGED, scope):
            charged[row.lease_id].add(Period.parse(row.period))
        return [
            LeaseToCharge(
                lease_id=row.id,
                due_day=row.due_day,
                start_date=row.start_date,
                control_from=Period.parse(row.control_from_period),
                ends_on=row.ends_on,
                rent_changes=tuple(changes[row.id]),
                charged=frozenset(charged[row.id]),
            )
            for row in await self._connection.execute(LEASES, scope)
        ]

    async def add_rent(
        self, account_id: UUID, charge_id: UUID, charge: RentCharge, created_at: datetime
    ) -> None:
        await self._connection.execute(
            ADD_RENT,
            {
                "id": charge_id,
                "account_id": account_id,
                "lease_id": charge.lease_id,
                "period": str(charge.period),
                "amount_cents": charge.amount_cents,
                "due_date": charge.due_date,
                "created_at": created_at,
            },
        )
