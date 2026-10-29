from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Row, text
from sqlalchemy.ext.asyncio import AsyncConnection

from casero.ledger.application.collections import LeaseBook
from casero.ledger.application.manual_charges import ChargeRecord
from casero.ledger.application.payments import LeaseLedger, NewPayment, PaymentRecord
from casero.ledger.domain.allocation import Charge, Payment
from casero.ledger.domain.charges import RentChange
from casero.shared.kernel.periods import Period

LEASE = text("SELECT id, control_from_period FROM leases WHERE id = :lease_id")
LOCK_LEASE = text("SELECT id FROM leases WHERE id = :lease_id FOR UPDATE")
LEASES = text("SELECT id, ended_at IS NOT NULL AS ended FROM leases")
RENT_CHANGES = text(
    "SELECT id, monthly_rent_cents, effective_period, created_at FROM lease_rent_changes"
    " WHERE lease_id = :lease_id"
)
SELECT_CHARGES = (
    "SELECT c.id, c.lease_id, c.kind, c.amount_cents, c.due_date, c.pre_2026, c.created_at,"
    " c.period, c.corrects_charge_id, v.charge_id IS NOT NULL AS voided FROM charges c"
    " LEFT JOIN charge_voids v ON v.charge_id = c.id"
)
CHARGES = text(SELECT_CHARGES + " WHERE c.lease_id = :lease_id")
ALL_CHARGES = text(SELECT_CHARGES)
CHARGE = text(SELECT_CHARGES + " WHERE c.id = :charge_id")
CORRECTION_OF = text("SELECT id FROM charges WHERE corrects_charge_id = :charge_id")
VALID_PRIOR_DEBT = text(
    "SELECT EXISTS (SELECT 1 FROM charges c WHERE c.lease_id = :lease_id"
    " AND c.kind = 'opening_balance' AND c.pre_2026 = :pre_2026"
    " AND NOT EXISTS (SELECT 1 FROM charge_voids v WHERE v.charge_id = c.id))"
)
LAST_RENT_PERIOD = text(
    "SELECT max(period) FROM charges WHERE lease_id = :lease_id"
    " AND kind IN ('rent', 'rent_correction')"
)
ADD_CHARGE = text(
    "INSERT INTO charges (id, account_id, lease_id, kind, period, amount_cents, due_date,"
    " corrects_charge_id, pre_2026, created_by, created_at) VALUES (:id, :account_id, :lease_id,"
    " :kind, :period, :amount_cents, :due_date, :corrects_charge_id, :pre_2026, :created_by,"
    " :created_at) ON CONFLICT (id) DO NOTHING RETURNING id"
)
VOID_CHARGE = text(
    "INSERT INTO charge_voids (charge_id, account_id, reason, voided_by, voided_at)"
    " VALUES (:charge_id, :account_id, :reason, :voided_by, :voided_at)"
    " ON CONFLICT (charge_id) DO NOTHING"
)
SELECT_PAYMENTS = (
    "SELECT p.id, p.lease_id, p.amount_cents, p.received_on, p.created_at, p.method, p.note,"
    " v.payment_id IS NOT NULL AS voided FROM payments p"
    " LEFT JOIN payment_voids v ON v.payment_id = p.id"
)
PAYMENTS = text(SELECT_PAYMENTS + " WHERE p.lease_id = :lease_id")
PAYMENT = text(SELECT_PAYMENTS + " WHERE p.id = :payment_id")
ALL_PAYMENTS = text(SELECT_PAYMENTS)
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


def charge(row: Row[Any]) -> Charge:
    return Charge(
        row.id,
        row.kind,
        row.amount_cents,
        row.due_date,
        row.pre_2026,
        row.created_at,
        row.voided,
        Period.parse(row.period) if row.period else None,
    )


def payment_record(row: Row[Any]) -> PaymentRecord:
    payment = Payment(row.id, row.amount_cents, row.received_on, row.created_at, row.voided)
    return PaymentRecord(payment, row.lease_id, row.method, row.note)


class SqlLedger:
    """Reads under RLS: only the account in context is visible."""

    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def lock_lease(self, lease_id: UUID) -> bool:
        locked = await self._connection.execute(LOCK_LEASE, {"lease_id": lease_id})
        return locked.first() is not None

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
        charges = [charge(row) for row in await self._connection.execute(CHARGES, scope)]
        payments = [payment_record(row) for row in await self._connection.execute(PAYMENTS, scope)]
        return LeaseLedger(
            lease.id, Period.parse(lease.control_from_period), changes, charges, payments
        )

    async def lease_books(self) -> list[LeaseBook]:
        books = {
            row.id: LeaseBook(row.id, row.ended, [], [])
            for row in await self._connection.execute(LEASES)
        }
        for row in await self._connection.execute(ALL_CHARGES):
            books[row.lease_id].charges.append(charge(row))
        for row in await self._connection.execute(ALL_PAYMENTS):
            books[row.lease_id].payments.append(payment_record(row).payment)
        return list(books.values())

    async def charge(self, charge_id: UUID) -> ChargeRecord | None:
        row = (await self._connection.execute(CHARGE, {"charge_id": charge_id})).first()
        if row is None:
            return None
        return ChargeRecord(charge(row), row.lease_id, row.corrects_charge_id)

    async def correction_of(self, charge_id: UUID) -> UUID | None:
        result = await self._connection.execute(CORRECTION_OF, {"charge_id": charge_id})
        correction: UUID | None = result.scalar_one_or_none()
        return correction

    async def valid_prior_debt(self, lease_id: UUID, pre_2026: bool) -> bool:
        result = await self._connection.execute(
            VALID_PRIOR_DEBT, {"lease_id": lease_id, "pre_2026": pre_2026}
        )
        exists: bool = result.scalar_one()
        return exists

    async def last_rent_period(self, lease_id: UUID) -> Period | None:
        result = await self._connection.execute(LAST_RENT_PERIOD, {"lease_id": lease_id})
        period: str | None = result.scalar_one()
        return Period.parse(period) if period else None

    async def add_charge(self, account_id: UUID, record: ChargeRecord, created_by: UUID) -> bool:
        new = record.charge
        inserted = await self._connection.execute(
            ADD_CHARGE,
            {
                "id": new.id,
                "account_id": account_id,
                "lease_id": record.lease_id,
                "kind": new.kind,
                "period": str(new.period) if new.period else None,
                "amount_cents": new.amount_cents,
                "due_date": new.due_date,
                "corrects_charge_id": record.corrects_charge_id,
                "pre_2026": new.pre_2026,
                "created_by": created_by,
                "created_at": new.created_at,
            },
        )
        return inserted.first() is not None

    async def void_charge(
        self, account_id: UUID, charge_id: UUID, reason: str, voided_by: UUID, at: datetime
    ) -> None:
        await self._connection.execute(
            VOID_CHARGE,
            {
                "charge_id": charge_id,
                "account_id": account_id,
                "reason": reason,
                "voided_by": voided_by,
                "voided_at": at,
            },
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
