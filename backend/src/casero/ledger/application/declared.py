from collections import defaultdict
from collections.abc import Sequence
from dataclasses import replace
from typing import Protocol
from uuid import UUID

from casero.ledger.domain.allocation import Charge, Payment, allocate, paid_toward_old_debt
from casero.shared.kernel.periods import Period


class DeclaredMonths(Protocol):
    """Implemented by tax (AR-03): which of these months the lease's tenant paid to SUNAT."""

    async def paid_to_sunat(self, lease_id: UUID, periods: Sequence[Period]) -> list[Period]: ...


def taxed_by_month(charges: list[Charge], payments: list[Payment]) -> dict[Period, int]:
    """Each month's collections that enter the tax base, with the allocation the tax uses."""
    old_debt = paid_toward_old_debt(allocate(charges, payments), charges)
    taxed: defaultdict[Period, int] = defaultdict(int)
    for payment in payments:
        if not payment.voided:
            month = Period.of(payment.received_on)
            taxed[month] += payment.amount_cents - old_debt.get(payment.id, 0)
    return dict(taxed)


def months_a_void_changes(
    charges: list[Charge],
    payments: list[Payment],
    *,
    charge_id: UUID | None = None,
    payment_id: UUID | None = None,
) -> list[Period]:
    """The months whose taxed collections differ with that charge or payment valid and voided.

    Not only the payment's own month: through the allocation, voiding a payment, a credit or
    the debt from 2025 or before changes how much of each later payment that debt takes.
    """

    def taxed(voided: bool) -> dict[Period, int]:
        return taxed_by_month(
            [replace(c, voided=voided) if c.id == charge_id else c for c in charges],
            [replace(p, voided=voided) if p.id == payment_id else p for p in payments],
        )

    valid, voided = taxed(False), taxed(True)
    return sorted(m for m in valid.keys() | voided.keys() if valid.get(m, 0) != voided.get(m, 0))
