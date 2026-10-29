from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from casero.ledger.application.collections import LeaseBook
from casero.ledger.application.payments import LeaseLedger, PaymentRecord
from casero.ledger.domain.allocation import allocate, paid_toward_old_debt
from casero.shared.kernel.periods import Period


@dataclass(frozen=True)
class CollectedPayment:
    payment_id: UUID
    lease_id: UUID
    received_on: date
    amount_cents: int
    old_debt_cents: int
    created_at: datetime

    @property
    def taxable_cents(self) -> int:
        return self.amount_cents - self.old_debt_cents


def collected_payments(books: Iterable[LeaseBook], period: Period) -> list[CollectedPayment]:
    """The month's valid payments, each with the part that paid debt from 2025 or before.

    Computed with the same allocation as the balances, so the tax and the statement agree.
    """
    collected = []
    for book in books:
        old_debt = paid_toward_old_debt(allocate(book.charges, book.payments), book.charges)
        collected += [
            CollectedPayment(
                payment.id,
                book.lease_id,
                payment.received_on,
                payment.amount_cents,
                old_debt.get(payment.id, 0),
                payment.created_at,
            )
            for payment in book.payments
            if not payment.voided and Period.of(payment.received_on) == period
        ]
    return collected


def rents_charged(
    books: Iterable[LeaseBook], first: Period, last: Period
) -> dict[UUID, dict[Period, int]]:
    """Each lease's rent per month: the valid rent, or the correction that replaced it."""
    rents: dict[UUID, dict[Period, int]] = {}
    for book in books:
        months: defaultdict[Period, int] = defaultdict(int)
        for charge in book.charges:
            if (
                charge.kind in ("rent", "rent_correction")
                and not charge.voided
                and charge.period is not None
                and first <= charge.period <= last
            ):
                months[charge.period] += charge.amount_cents
        rents[book.lease_id] = dict(months)
    return rents


@dataclass(frozen=True)
class ReceivedPayment:
    record: PaymentRecord
    old_debt_cents: int


def received_payments(ledger: LeaseLedger) -> list[ReceivedPayment]:
    """A lease's valid payments, each with the part that paid debt from 2025 or before."""
    payments = [record.payment for record in ledger.payments]
    old_debt = paid_toward_old_debt(allocate(ledger.charges, payments), ledger.charges)
    return [
        ReceivedPayment(record, old_debt.get(record.payment.id, 0))
        for record in ledger.payments
        if not record.payment.voided
    ]
