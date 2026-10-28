from datetime import date, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from casero.leases.application.leases import OpeningBalances

OPENING_BALANCES = text(
    "SELECT pre_2026, amount_cents FROM charges"
    " WHERE lease_id = :lease_id AND kind = 'opening_balance'"
)
ADD_OPENING_BALANCE = text(
    "INSERT INTO charges (id, account_id, lease_id, kind, amount_cents, due_date, pre_2026,"
    " created_by, created_at) VALUES (:id, :account_id, :lease_id, 'opening_balance',"
    " :amount_cents, :due_date, :pre_2026, :created_by, :created_at)"
)


class SqlOpeningBalances:
    """Reads under RLS: only the charges of the account in context are visible."""

    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def opening_balances(self, lease_id: UUID) -> OpeningBalances:
        rows = await self._connection.execute(OPENING_BALANCES, {"lease_id": lease_id})
        amounts = {row.pre_2026: row.amount_cents for row in rows}
        return OpeningBalances(amounts.get(True), amounts.get(False))

    async def add_opening_balance(
        self,
        account_id: UUID,
        charge_id: UUID,
        lease_id: UUID,
        amount_cents: int,
        pre_2026: bool,
        due_date: date,
        created_by: UUID,
        created_at: datetime,
    ) -> None:
        await self._connection.execute(
            ADD_OPENING_BALANCE,
            {
                "id": charge_id,
                "account_id": account_id,
                "lease_id": lease_id,
                "amount_cents": amount_cents,
                "due_date": due_date,
                "pre_2026": pre_2026,
                "created_by": created_by,
                "created_at": created_at,
            },
        )
