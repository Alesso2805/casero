from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol
from uuid import UUID

from casero.shared.kernel.periods import Period


@dataclass(frozen=True)
class NewTaxPayment:
    id: UUID
    period: Period
    renter_id: UUID
    amount_cents: int
    paid_on: date
    order_number: str


@dataclass(frozen=True)
class TaxPaymentRecord:
    id: UUID
    period: Period
    renter_id: UUID
    renter_doc_hmac: bytes
    amount_cents: int
    paid_on: date
    order_number: str
    base_cents: int
    created_at: datetime
    voided: bool

    def matches(self, new: NewTaxPayment) -> bool:
        return (
            self.period,
            self.renter_id,
            self.amount_cents,
            self.paid_on,
            self.order_number,
        ) == (new.period, new.renter_id, new.amount_cents, new.paid_on, new.order_number)


class TaxPaymentStore(Protocol):
    async def add(
        self,
        account_id: UUID,
        new: NewTaxPayment,
        renter_doc_hmac: bytes,
        base_cents: int,
        created_by: UUID,
        created_at: datetime,
    ) -> bool:
        """False when the id already exists, in this account or another (rule 5)."""
        ...

    async def get(self, payment_id: UUID) -> TaxPaymentRecord | None: ...

    async def of_period(self, period: Period) -> list[TaxPaymentRecord]: ...

    async def void(
        self, account_id: UUID, payment_id: UUID, reason: str, voided_by: UUID, at: datetime
    ) -> bool:
        """False when it was already voided."""
        ...
