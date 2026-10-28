from datetime import date, timedelta
from uuid import UUID

import pytest
from hypothesis import given
from hypothesis import strategies as st

from casero.leases.domain.leases import (
    Lease,
    LeaseTerms,
    OpeningBalances,
    control_period_range,
    effective_treatment,
    lease_problem,
    opening_balance_due,
)
from casero.shared.kernel.periods import FIRST_CONTROL_PERIOD, Period

TODAY = date(2026, 10, 27)
NO_BALANCES = OpeningBalances(None, None)


def terms(**overrides: object) -> LeaseTerms:
    values: dict[str, object] = {
        "unit_id": UUID(int=1),
        "renter_id": UUID(int=2),
        "monthly_rent_cents": 80_000,
        "due_day": 5,
        "start_date": date(2026, 3, 1),
        "end_date": None,
        "control_from": Period(2026, 10),
        "tax_treatment": "standard",
    }
    return LeaseTerms(**{**values, **overrides})  # type: ignore[arg-type]


def test_periods_read_and_write_as_year_and_month() -> None:
    assert str(Period.parse("2026-02")) == "2026-02"
    assert Period.of(date(2026, 12, 31)).next() == Period(2027, 1)
    assert Period(2028, 2).last_day() == date(2028, 2, 29)
    for text in ("2026-13", "2026-1", "26-01"):
        with pytest.raises(ValueError, match="period"):
            Period.parse(text)


@pytest.mark.parametrize(
    ("start", "low", "high"),
    [
        (date(2025, 6, 1), FIRST_CONTROL_PERIOD, Period(2026, 10)),
        (date(2026, 5, 15), Period(2026, 5), Period(2026, 10)),
        (date(2026, 10, 27), Period(2026, 10), Period(2026, 10)),
        (date(2026, 12, 5), Period(2026, 12), Period(2026, 12)),
    ],
)
def test_the_control_month_follows_the_start(start: date, low: Period, high: Period) -> None:
    assert control_period_range(start, TODAY) == (low, high)


@given(st.dates(min_value=date(2020, 1, 1), max_value=date(2027, 12, 31)))
def test_the_default_control_month_is_always_allowed(start: date) -> None:
    default = Period.of(TODAY) if start <= TODAY else Period.of(start)
    low, high = control_period_range(start, TODAY)

    assert low <= default <= high
    assert low >= FIRST_CONTROL_PERIOD


@pytest.mark.parametrize(
    ("lease", "opening", "problem"),
    [
        (terms(end_date=date(2026, 2, 28)), NO_BALANCES, "end_before_start"),
        (terms(control_from=Period(2026, 2)), NO_BALANCES, "control_period_out_of_range"),
        (terms(control_from=Period(2026, 11)), NO_BALANCES, "control_period_out_of_range"),
        (
            terms(start_date=date(2025, 6, 1), control_from=FIRST_CONTROL_PERIOD),
            OpeningBalances(None, 50_000),
            "balance_2026_without_months",
        ),
        (terms(), OpeningBalances(120_000, 50_000), None),
    ],
)
def test_lease_problems(lease: LeaseTerms, opening: OpeningBalances, problem: str | None) -> None:
    assert lease_problem(lease, opening, TODAY) == problem


def test_spouses_declaring_halves_force_the_unsupported_treatment() -> None:
    assert effective_treatment("company_tenant", split_by_spouses=True) == "unsupported"
    assert effective_treatment("company_tenant", split_by_spouses=False) == "company_tenant"


@pytest.mark.parametrize(
    ("pre_2026", "control", "due"),
    [
        (True, Period(2026, 11), date(2025, 12, 31)),
        (False, Period(2026, 11), date(2026, 10, 31)),
        (False, Period(2026, 3), date(2026, 2, 28)),
    ],
)
def test_prior_balances_are_already_due(pre_2026: bool, control: Period, due: date) -> None:
    assert opening_balance_due(pre_2026, control) == due


@pytest.mark.parametrize(
    ("end", "ended", "days", "soon"),
    [
        (TODAY + timedelta(days=15), None, 15, True),
        (TODAY + timedelta(days=16), None, 16, False),
        (TODAY - timedelta(days=1), None, -1, False),
        (TODAY + timedelta(days=3), date(2026, 10, 1), None, False),
        (None, None, None, False),
    ],
)
def test_the_end_notice_starts_15_days_before(
    end: date | None, ended: date | None, days: int | None, soon: bool
) -> None:
    lease = Lease(UUID(int=3), terms(end_date=end), ended, 80_000)

    assert (lease.days_to_end(TODAY), lease.ending_soon(TODAY)) == (days, soon)
