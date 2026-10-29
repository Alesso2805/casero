from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from casero.shared.kernel.periods import Period


@dataclass(frozen=True)
class RentChange:
    id: UUID
    monthly_rent_cents: int
    effective_period: Period
    created_at: datetime


@dataclass(frozen=True)
class LeaseToCharge:
    lease_id: UUID
    due_day: int
    start_date: date
    control_from: Period
    ends_on: date | None
    rent_changes: tuple[RentChange, ...]
    charged: frozenset[Period]


@dataclass(frozen=True)
class RentCharge:
    lease_id: UUID
    period: Period
    amount_cents: int
    due_date: date


def rent_due_date(period: Period, due_day: int, start_date: date) -> date:
    """The payment day, or the month's last day if it has no such day, never before the start."""
    due = date(period.year, period.month, min(due_day, period.last_day().day))
    return max(due, start_date)


def rent_for(period: Period, changes: tuple[RentChange, ...]) -> int:
    """The change with the latest (effective_period, created_at) up to the period (SPEC).

    Before the first effective period (prior debt collected before control began) it is the
    rent of that first period with its latest correction, as the leases list shows it.
    """
    first = min(change.effective_period for change in changes)
    latest = max(
        (change for change in changes if change.effective_period <= max(period, first)),
        key=lambda change: (change.effective_period, change.created_at, change.id),
    )
    return latest.monthly_rent_cents


def missing_rent_charges(lease: LeaseToCharge, today: date) -> list[RentCharge]:
    """Every period from the control month to today, or to the period holding the lease's end.

    A period whose first day falls on or before the end is charged in full (SPEC, "Último
    mes"). A period that already has a rent charge, voided or not, is never charged again.
    """
    last = Period.of(today)
    if lease.ends_on is not None:
        last = min(last, Period.of(lease.ends_on))
    charges: list[RentCharge] = []
    period = lease.control_from
    while period <= last:
        if period not in lease.charged:
            charges.append(
                RentCharge(
                    lease.lease_id,
                    period,
                    rent_for(period, lease.rent_changes),
                    rent_due_date(period, lease.due_day, lease.start_date),
                )
            )
        period = period.next()
    return charges
