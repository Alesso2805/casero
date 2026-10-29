from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

ChangeKind = Literal["up", "down", "document_changed", "overdue_unpaid"]


@dataclass(frozen=True)
class PaidDeclaration:
    """One valid SUNAT payment, with the base Casero showed when it was recorded."""

    base_cents: int
    amount_cents: int
    created_at: datetime


@dataclass(frozen=True)
class AfterDeclaring:
    kind: ChangeKind
    base_difference_cents: int = 0
    tax_difference_cents: int = 0


def after_declaring(
    base_cents: int,
    tax_cents: int,
    paid: list[PaidDeclaration],
    paid_with_another_document: bool,
    due_on: date | None,
    today: date,
) -> AfterDeclaring | None:
    """Which of SPEC's texts the card needs after the landlord declared (or should have).

    The latest payment's base is what was last declared; a rectification restates the whole
    month, so earlier payments don't matter for the comparison.
    """
    if paid_with_another_document:
        return AfterDeclaring("document_changed")
    if paid:
        declared = max(paid, key=lambda payment: payment.created_at).base_cents
        if base_cents > declared:
            owed = tax_cents - sum(payment.amount_cents for payment in paid)
            return AfterDeclaring("up", base_cents - declared, max(owed, 0))
        if base_cents < declared:
            return AfterDeclaring("down", declared - base_cents)
        return None
    if due_on is not None and due_on < today and tax_cents > 0:
        return AfterDeclaring("overdue_unpaid")
    return None
