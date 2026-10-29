from dataclasses import dataclass
from datetime import date
from uuid import UUID

from casero.ledger.application.collections import CollectionsStore
from casero.ledger.domain.allocation import allocate, paid_toward_old_debt
from casero.shared.kernel.periods import Period


@dataclass(frozen=True)
class CollectedPayment:
    payment_id: UUID
    lease_id: UUID
    received_on: date
    amount_cents: int
    old_debt_cents: int

    @property
    def taxable_cents(self) -> int:
        return self.amount_cents - self.old_debt_cents


@dataclass(frozen=True)
class CollectedPayments:
    """The month's valid payments, each with the part that paid debt from 2025 or before.

    Computed with the same allocation as the balances, so the tax and the statement agree.
    """

    store: CollectionsStore

    async def __call__(self, period: Period) -> list[CollectedPayment]:
        collected = []
        for book in await self.store.lease_books():
            old_debt = paid_toward_old_debt(allocate(book.charges, book.payments), book.charges)
            collected += [
                CollectedPayment(
                    payment.id,
                    book.lease_id,
                    payment.received_on,
                    payment.amount_cents,
                    old_debt.get(payment.id, 0),
                )
                for payment in book.payments
                if not payment.voided and Period.of(payment.received_on) == period
            ]
        return collected
