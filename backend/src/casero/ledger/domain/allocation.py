from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal
from uuid import UUID

from casero.shared.kernel.clock import LIMA
from casero.shared.kernel.periods import Period

ChargeKind = Literal["rent", "rent_correction", "opening_balance", "adjustment"]
ChargeStatus = Literal["paid", "overdue", "due_today", "due_soon", "pending"]
MovementKind = Literal["payment", "credit"]
# Payments and credits are separate tables whose client-generated ids could repeat.
type Source = tuple[MovementKind, UUID]
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
    period: Period | None = None
    corrects_charge_id: UUID | None = None

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
    def source(self) -> Source:
        return ("credit" if self.is_credit else "payment", self.id)

    @property
    def order(self) -> tuple[date, bool, datetime, UUID]:
        # Same date: every payment before every credit, each group by (created_at, id).
        return (self.effective_on, self.is_credit, self.created_at, self.id)


@dataclass(frozen=True)
class Allocation:
    outstanding: dict[UUID, int]
    covered: dict[tuple[Source, UUID], int]
    unapplied_cents: int
    balance_cents: int

    def covered_by(self, source: Source) -> dict[UUID, int]:
        return {
            charge: cents
            for (covering, charge), cents in self.covered.items()
            if covering == source
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
    covered: defaultdict[tuple[Source, UUID], int] = defaultdict(int)
    unapplied = 0
    for move in movements(charges, payments):
        remaining = move.amount_cents
        for debit in debits:
            if remaining == 0:
                break
            take = min(remaining, outstanding[debit.id])
            if take:
                outstanding[debit.id] -= take
                covered[(move.source, debit.id)] += take
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


def paid_toward_old_debt(allocation: Allocation, charges: list[Charge]) -> dict[UUID, int]:
    """What each payment paid of the debt from 2025 or before.

    That debt was taxed when it accrued, so collecting it is not taxed again (SPEC,
    "Deudas de 2025 o antes"). Credits are never money collected and are left out.
    """
    old_debt = {
        c.id for c in charges if c.kind == "opening_balance" and c.pre_2026 and not c.voided
    }
    paid: defaultdict[UUID, int] = defaultdict(int)
    for ((kind, movement_id), charge_id), cents in allocation.covered.items():
        if kind == "payment" and charge_id in old_debt:
            paid[movement_id] += cents
    return dict(paid)
