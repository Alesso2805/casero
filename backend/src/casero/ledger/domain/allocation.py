from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal
from uuid import UUID

from casero.shared.kernel.clock import LIMA

ChargeKind = Literal["rent", "rent_correction", "opening_balance", "adjustment"]
ChargeStatus = Literal["paid", "overdue", "due_today", "due_soon", "pending"]
DUE_SOON = timedelta(days=3)


@dataclass(frozen=True)
class Charge:
    id: UUID
    kind: ChargeKind
    amount_cents: int
    due_date: date
    pre_2026: bool | None
    created_at: datetime
    voided: bool = False

    @property
    def is_credit(self) -> bool:
        return self.kind == "adjustment" and self.amount_cents < 0


@dataclass(frozen=True)
class Payment:
    id: UUID
    amount_cents: int
    received_on: date
    created_at: datetime
    voided: bool = False


@dataclass(frozen=True)
class Movement:
    """A payment, or a credit (a negative adjustment), in the order SPEC applies them."""

    id: UUID
    is_credit: bool
    amount_cents: int
    effective_on: date
    created_at: datetime

    @property
    def order(self) -> tuple[date, bool, datetime, UUID]:
        # Same date: every payment before every credit, each group by (created_at, id).
        return (self.effective_on, self.is_credit, self.created_at, self.id)


@dataclass(frozen=True)
class Allocation:
    outstanding: dict[UUID, int]
    covered: dict[tuple[UUID, UUID], int]
    unapplied_cents: int
    balance_cents: int

    def covered_by(self, movement_id: UUID) -> dict[UUID, int]:
        return {
            charge: cents
            for (movement, charge), cents in self.covered.items()
            if movement == movement_id
        }


def debit_order(charge: Charge) -> tuple[int, date, datetime, UUID]:
    """Debt from 2025 or before first, then 2026's prior debt, then by due date (SPEC)."""
    era = 2
    if charge.kind == "opening_balance":
        era = 0 if charge.pre_2026 else 1
    return (era, charge.due_date, charge.created_at, charge.id)


def movements(charges: list[Charge], payments: list[Payment]) -> list[Movement]:
    """Valid payments and credits; a credit takes effect on the Lima date it was recorded."""
    moves = [
        Movement(payment.id, False, payment.amount_cents, payment.received_on, payment.created_at)
        for payment in payments
        if not payment.voided
    ]
    moves += [
        Movement(
            charge.id,
            True,
            -charge.amount_cents,
            charge.created_at.astimezone(LIMA).date(),
            charge.created_at,
        )
        for charge in charges
        if charge.is_credit and not charge.voided
    ]
    return sorted(moves, key=lambda move: move.order)


def allocate(charges: list[Charge], payments: list[Payment]) -> Allocation:
    """Applies payments and credits to charges as SPEC "Aplicación" says.

    Each movement covers what earlier movements left pending, so a movement never changes
    how the ones before it were applied, and what is left over stays as credit in favor.
    """
    debits = sorted(
        (c for c in charges if not c.voided and not c.is_credit and c.amount_cents > 0),
        key=debit_order,
    )
    outstanding = {debit.id: debit.amount_cents for debit in debits}
    covered: defaultdict[tuple[UUID, UUID], int] = defaultdict(int)
    unapplied = 0
    for move in movements(charges, payments):
        remaining = move.amount_cents
        for debit in debits:
            if remaining == 0:
                break
            take = min(remaining, outstanding[debit.id])
            if take:
                outstanding[debit.id] -= take
                covered[(move.id, debit.id)] += take
                remaining -= take
        unapplied += remaining
    balance = sum(c.amount_cents for c in charges if not c.voided) - sum(
        p.amount_cents for p in payments if not p.voided
    )
    return Allocation(outstanding, dict(covered), unapplied, balance)


def charge_status(due_date: date, outstanding_cents: int, today: date) -> ChargeStatus:
    """In SPEC's order of precedence; "partial" is a separate attribute."""
    if outstanding_cents <= 0:
        return "paid"
    if today > due_date:
        return "overdue"
    if today == due_date:
        return "due_today"
    if due_date - today <= DUE_SOON:
        return "due_soon"
    return "pending"
