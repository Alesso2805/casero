from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Row, text
from sqlalchemy.ext.asyncio import AsyncConnection

from casero.ledger.application.payments import LeaseLedger, NewPayment, PaymentRecord
from casero.ledger.domain.allocation import Charge, Payment
from casero.ledger.domain.charges import RentChange
from casero.shared.kernel.periods import Period

LEASE = text("SELECT id, control_from_period FROM leases WHERE id = :lease_id")
RENT_CHANGES = text(
    "SELECT id, monthly_rent_cents, effective_period, created_at FROM lease_rent_changes"
    " WHERE lease_id = :lease_id"
)
CHARGES = text(
    "SELECT c.id, c.kind, c.amount_cents, c.due_date, c.pre_2026, c.created_at, c.period,"
    " v.charge_id IS NOT NULL AS voided FROM charges c"
    " LEFT JOIN charge_voids v ON v.charge_id = c.id WHERE c.lease_id = :lease_id"
)
SELECT_PAYMENTS = (
    "SELECT p.id, p.lease_id, p.amount_cents, p.received_on, p.created_at, p.method, p.note,"
    " v.payment_id IS NOT NULL AS voided FROM payments p"
    " LEFT JOIN payment_voids v ON v.payment_id = p.id"
)
PAYMENTS = text(SELECT_PAYMENTS + " WHERE p.lease_id = :lease_id")
PAYMENT = text(SELECT_PAYMENTS + " WHERE p.id = :payment_id")
ADD_PAYMENT = text(
    "INSERT INTO payments (id, account_id, lease_id, amount_cents, received_on, method, note,"
    " source, created_by, created_at) VALUES (:id, :account_id, :lease_id, :amount_cents,"
    " :received_on, :method, :note, 'landlord', :created_by, :created_at)"
    " ON CONFLICT (id) DO NOTHING RETURNING id"
)
VOID_PAYMENT = text(
    "INSERT INTO payment_voids (payment_id, account_id, reason, voided_by, voided_at)"
    " VALUES (:payment_id, :account_id, :reason, :voided_by, :voided_at)"
    " ON CONFLICT (payment_id) DO NOTHING"
)


def payment_record(row: Row[Any]) -> PaymentRecord:
    payment = Payment(row.id, row.amount_cents, row.received_on, row.created_at, row.voided)
    return PaymentRecord(payment, row.lease_id, row.method, row.note)


class SqlLedger:
    """Reads under RLS: only the account in context is visible."""

    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def lease_ledger(self, lease_id: UUID) -> LeaseLedger | None:
        scope = {"lease_id": lease_id}
        lease = (await self._connection.execute(LEASE, scope)).first()
        if lease is None:
            return None
        changes = tuple(
            RentChange(
                row.id, row.monthly_rent_cents, Period.parse(row.effective_period), row.created_at
            )
            for row in await self._connection.execute(RENT_CHANGES, scope)
        )
        charges = [
            Charge(
                row.id,
                row.kind,
                row.amount_cents,
                row.due_date,
                row.pre_2026,
                row.created_at,
                row.voided,
                Period.parse(row.period) if row.period else None,
            )
            for row in await self._connection.execute(CHARGES, scope)
        ]
        payments = [payment_record(row) for row in await self._connection.execute(PAYMENTS, scope)]
        return LeaseLedger(
            lease.id, Period.parse(lease.control_from_period), changes, charges, payments
        )

    async def payment(self, payment_id: UUID) -> PaymentRecord | None:
        row = (await self._connection.execute(PAYMENT, {"payment_id": payment_id})).first()
        return None if row is None else payment_record(row)

    async def add_payment(
        self, account_id: UUID, new: NewPayment, created_by: UUID, created_at: datetime
    ) -> bool:
        inserted = await self._connection.execute(
            ADD_PAYMENT,
            {
                "id": new.id,
                "account_id": account_id,
                "lease_id": new.lease_id,
                "amount_cents": new.amount_cents,
                "received_on": new.received_on,
                "method": new.method,
                "note": new.note,
                "created_by": created_by,
                "created_at": created_at,
            },
        )
        return inserted.first() is not None

    async def void_payment(
        self, account_id: UUID, payment_id: UUID, reason: str, voided_by: UUID, at: datetime
    ) -> None:
        await self._connection.execute(
            VOID_PAYMENT,
            {
                "payment_id": payment_id,
                "account_id": account_id,
                "reason": reason,
                "voided_by": voided_by,
                "voided_at": at,
            },
        )
