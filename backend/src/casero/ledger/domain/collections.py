from dataclasses import dataclass
from datetime import date
from typing import Literal

from casero.ledger.domain.allocation import Charge, Payment, allocate, charge_status
from casero.shared.kernel.periods import Period

Standing = Literal["overdue", "due_today", "due_soon", "up_to_date"]
URGENCY: tuple[Standing, ...] = ("overdue", "due_today", "due_soon", "up_to_date")


@dataclass(frozen=True)
class LeaseCollection:
    status: Standing
    overdue_days: int
    overdue_cents: int
    next_due_on: date | None
    next_due_cents: int
    due_by_month_end_cents: int
    balance_cents: int
    rent_to_remind: bool


def collection(charges: list[Charge], payments: list[Payment], today: date) -> LeaseCollection:
    """Where a lease stands today: up to date means nothing overdue (SPEC, "Estado")."""
    allocation = allocate(charges, payments)
    month_end = Period.of(today).last_day()
    oldest_overdue: date | None = None
    overdue = by_month_end = 0
    upcoming: dict[date, int] = {}
    rent_to_remind = False
    for charge in charges:
        if charge.voided or charge.is_credit or allocation.outstanding[charge.id] == 0:
            continue
        left = allocation.outstanding[charge.id]
        rent_to_remind = rent_to_remind or charge.kind in ("rent", "rent_correction")
        if charge.due_date <= month_end:
            by_month_end += left
        if charge_status(charge.due_date, left, today) == "overdue":
            overdue += left
            oldest_overdue = min(oldest_overdue or charge.due_date, charge.due_date)
        else:
            upcoming[charge.due_date] = upcoming.get(charge.due_date, 0) + left
    next_due_on = min(upcoming, default=None)
    return LeaseCollection(
        status=standing(oldest_overdue is not None, next_due_on, today),
        overdue_days=(today - oldest_overdue).days if oldest_overdue else 0,
        overdue_cents=overdue,
        next_due_on=next_due_on,
        next_due_cents=upcoming.get(next_due_on, 0) if next_due_on else 0,
        due_by_month_end_cents=by_month_end,
        balance_cents=allocation.balance_cents,
        rent_to_remind=rent_to_remind,
    )


def standing(overdue: bool, next_due_on: date | None, today: date) -> Standing:
    if overdue:
        return "overdue"
    if next_due_on == today:
        return "due_today"
    if next_due_on is not None and charge_status(next_due_on, 1, today) == "due_soon":
        return "due_soon"
    return "up_to_date"
