from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from casero.shared.kernel.periods import Period
from casero.tax.domain.assessment import assess
from casero.tax.domain.rules import TaxRules


@dataclass(frozen=True)
class Declarant:
    """Whose Formulario 1683 it is: the tenant's document, or the tenant while it lacks one."""

    doc_hmac: bytes | None
    renter_id: UUID

    @property
    def key(self) -> bytes | UUID:
        # One declaration per document and month, adding up all of that tenant's leases (SPEC).
        return self.doc_hmac if self.doc_hmac is not None else self.renter_id


@dataclass(frozen=True)
class TaxablePayment:
    """A payment of a lease that enters declarations: standard or company tenant."""

    declarant: Declarant
    lease_id: UUID
    received_on: date
    taxable_cents: int
    old_debt_cents: int


@dataclass(frozen=True)
class Declaration:
    declarant: Declarant
    period: Period
    lease_ids: tuple[UUID, ...]
    collected_cents: int
    old_debt_cents: int
    base_cents: int
    tax_cents: int

    @property
    def incomplete(self) -> bool:
        """Without the tenant's document the 1683 cannot be filed (SPEC)."""
        return self.declarant.doc_hmac is None


def declarations(
    payments: Iterable[TaxablePayment], period: Period, rules: TaxRules
) -> list[Declaration]:
    """The month's declarations: what was collected from each tenant, on the year's rules.

    The part of a payment that paid debt from 2025 or before is shown apart and never
    enters the base (SPEC, "Deudas de 2025 o antes").
    """
    groups: dict[bytes | UUID, list[TaxablePayment]] = {}
    for payment in payments:
        if Period.of(payment.received_on) == period:
            groups.setdefault(payment.declarant.key, []).append(payment)
    result = []
    for group in groups.values():
        collected = sum(p.taxable_cents for p in group)
        assessment = assess(collected, rules)
        result.append(
            Declaration(
                declarant=group[0].declarant,
                period=period,
                lease_ids=tuple(sorted({p.lease_id for p in group})),
                collected_cents=collected,
                old_debt_cents=sum(p.old_debt_cents for p in group),
                base_cents=assessment.base_cents,
                tax_cents=assessment.tax_cents,
            )
        )
    return sorted(result, key=lambda d: (d.incomplete, str(d.declarant.key)))
