from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal
from uuid import UUID

from casero.shared.kernel.periods import FIRST_CONTROL_PERIOD, Period

TaxTreatment = Literal["standard", "company_tenant", "unsupported"]
LeaseProblem = Literal[
    "end_before_start", "control_period_out_of_range", "balance_2026_without_months"
]

END_NOTICE_DAYS = 15


@dataclass(frozen=True)
class OpeningBalances:
    pre_2026_cents: int | None
    from_2026_cents: int | None


@dataclass(frozen=True)
class LeaseTerms:
    unit_id: UUID
    renter_id: UUID
    monthly_rent_cents: int
    due_day: int
    start_date: date
    end_date: date | None
    control_from: Period
    tax_treatment: TaxTreatment


def control_period_range(start_date: date, today: date) -> tuple[Period, Period]:
    """A past start lets the landlord pick the control month; a future one fixes it."""
    start = Period.of(start_date)
    if start_date > today:
        return start, start
    return max(start, FIRST_CONTROL_PERIOD), Period.of(today)


def lease_problem(terms: LeaseTerms, opening: OpeningBalances, today: date) -> LeaseProblem | None:
    if terms.end_date is not None and terms.end_date < terms.start_date:
        return "end_before_start"
    low, high = control_period_range(terms.start_date, today)
    if not low <= terms.control_from <= high:
        return "control_period_out_of_range"
    if opening.from_2026_cents and terms.control_from <= FIRST_CONTROL_PERIOD:
        return "balance_2026_without_months"
    return None


def effective_treatment(requested: TaxTreatment, split_by_spouses: bool) -> TaxTreatment:
    """Each spouse declaring half is outside the MVP, so its leases never enter declarations."""
    return "unsupported" if split_by_spouses else requested


def opening_balance_due(pre_2026: bool, control_from: Period) -> date:
    """Prior debt is already overdue: the day before its stretch of months ends."""
    boundary = FIRST_CONTROL_PERIOD if pre_2026 else control_from
    return boundary.first_day() - timedelta(days=1)


@dataclass(frozen=True)
class Lease:
    id: UUID
    terms: LeaseTerms
    ended_at: date | None
    current_rent_cents: int

    def days_to_end(self, today: date) -> int | None:
        if self.terms.end_date is None or self.ended_at is not None:
            return None
        return (self.terms.end_date - today).days

    def ending_soon(self, today: date) -> bool:
        days = self.days_to_end(today)
        return days is not None and 0 <= days <= END_NOTICE_DAYS
