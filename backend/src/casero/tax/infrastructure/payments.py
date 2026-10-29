from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Row, text
from sqlalchemy.ext.asyncio import AsyncConnection

from casero.shared.kernel.periods import Period
from casero.tax.application.sunat_payments import NewTaxPayment, TaxPaymentRecord

SELECT_PAYMENTS = (
    "SELECT p.id, p.period, p.renter_id, p.renter_doc_hmac, p.amount_cents, p.paid_on,"
    " p.order_number, p.base_cents, p.created_at, v.tax_payment_id IS NOT NULL AS voided"
    " FROM tax_payments p LEFT JOIN tax_payment_voids v"
    " ON v.account_id = p.account_id AND v.tax_payment_id = p.id"
)
PAYMENT = text(SELECT_PAYMENTS + " WHERE p.id = :id")
OF_PERIOD = text(SELECT_PAYMENTS + " WHERE p.period = :period ORDER BY p.created_at, p.id")
ADD = text(
    "INSERT INTO tax_payments (id, account_id, period, renter_doc_hmac, renter_id, amount_cents,"
    " paid_on, order_number, base_cents, created_by, created_at) VALUES (:id, :account_id,"
    " :period, :renter_doc_hmac, :renter_id, :amount_cents, :paid_on, :order_number,"
    " :base_cents, :created_by, :created_at) ON CONFLICT (id) DO NOTHING RETURNING id"
)
# The declaration is the tenant's document; a payment made before it changed is still theirs.
PAID_TO_SUNAT = text(
    "SELECT DISTINCT p.period FROM leases l"
    " JOIN renters r ON r.account_id = l.account_id AND r.id = l.renter_id"
    " JOIN tax_payments p ON p.account_id = l.account_id"
    " AND (p.renter_id = r.id OR p.renter_doc_hmac = r.doc_hmac)"
    " WHERE l.id = :lease_id AND l.tax_treatment <> 'unsupported' AND p.period = ANY(:periods)"
    " AND NOT EXISTS (SELECT 1 FROM tax_payment_voids v"
    " WHERE v.account_id = p.account_id AND v.tax_payment_id = p.id)"
    " ORDER BY p.period"
)
VOID = text(
    "INSERT INTO tax_payment_voids (tax_payment_id, account_id, reason, voided_by, voided_at)"
    " VALUES (:id, :account_id, :reason, :voided_by, :voided_at)"
    " ON CONFLICT (tax_payment_id) DO NOTHING RETURNING tax_payment_id"
)


def record(row: Row[Any]) -> TaxPaymentRecord:
    return TaxPaymentRecord(
        row.id,
        Period.parse(row.period),
        row.renter_id,
        bytes(row.renter_doc_hmac),
        row.amount_cents,
        row.paid_on,
        row.order_number,
        row.base_cents,
        row.created_at,
        row.voided,
    )


class SqlTaxPayments:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def add(
        self,
        account_id: UUID,
        new: NewTaxPayment,
        renter_doc_hmac: bytes,
        base_cents: int,
        created_by: UUID,
        created_at: datetime,
    ) -> bool:
        inserted = await self._connection.execute(
            ADD,
            {
                "id": new.id,
                "account_id": account_id,
                "period": str(new.period),
                "renter_doc_hmac": renter_doc_hmac,
                "renter_id": new.renter_id,
                "amount_cents": new.amount_cents,
                "paid_on": new.paid_on,
                "order_number": new.order_number,
                "base_cents": base_cents,
                "created_by": created_by,
                "created_at": created_at,
            },
        )
        return inserted.first() is not None

    async def get(self, payment_id: UUID) -> TaxPaymentRecord | None:
        row = (await self._connection.execute(PAYMENT, {"id": payment_id})).first()
        return None if row is None else record(row)

    async def of_period(self, period: Period) -> list[TaxPaymentRecord]:
        rows = await self._connection.execute(OF_PERIOD, {"period": str(period)})
        return [record(row) for row in rows]

    async def paid_to_sunat(self, lease_id: UUID, periods: Sequence[Period]) -> list[Period]:
        rows = await self._connection.execute(
            PAID_TO_SUNAT, {"lease_id": lease_id, "periods": [str(p) for p in periods]}
        )
        return [Period.parse(row.period) for row in rows]

    async def void(
        self, account_id: UUID, payment_id: UUID, reason: str, voided_by: UUID, at: datetime
    ) -> bool:
        voided = await self._connection.execute(
            VOID,
            {
                "id": payment_id,
                "account_id": account_id,
                "reason": reason,
                "voided_by": voided_by,
                "voided_at": at,
            },
        )
        return voided.first() is not None
