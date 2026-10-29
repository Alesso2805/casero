from datetime import UTC, date, datetime
from uuid import UUID

import pytest
from hypothesis import given
from hypothesis import strategies as st

from casero.ledger.domain.charges import (
    LeaseToCharge,
    RentChange,
    missing_rent_charges,
    rent_due_date,
    rent_for,
)
from casero.shared.kernel.periods import Period

LEASE_ID = UUID(int=1)
CREATED = datetime(2026, 9, 1, tzinfo=UTC)
FIRST_RENT = RentChange(UUID(int=10), 80_000, Period(2026, 9), CREATED)


def lease(**overrides: object) -> LeaseToCharge:
    values: dict[str, object] = {
        "lease_id": LEASE_ID,
        "due_day": 5,
        "start_date": date(2025, 6, 1),
        "control_from": Period(2026, 9),
        "ends_on": None,
        "rent_changes": (FIRST_RENT,),
        "charged": frozenset(),
    }
    return LeaseToCharge(**{**values, **overrides})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("period", "due_day", "start", "due"),
    [
        (Period(2026, 10), 5, date(2025, 6, 1), date(2026, 10, 5)),
        (Period(2026, 4), 31, date(2025, 6, 1), date(2026, 4, 30)),
        (Period(2027, 2), 31, date(2025, 6, 1), date(2027, 2, 28)),
        (Period(2028, 2), 30, date(2025, 6, 1), date(2028, 2, 29)),
        (Period(2026, 10), 5, date(2026, 10, 20), date(2026, 10, 20)),
        (Period(2026, 11), 5, date(2026, 10, 20), date(2026, 11, 5)),
    ],
)
def test_the_due_date_fits_the_month_and_never_precedes_the_start(
    period: Period, due_day: int, start: date, due: date
) -> None:
    assert rent_due_date(period, due_day, start) == due


def test_the_rent_of_a_period_is_the_latest_change_up_to_it() -> None:
    raised = RentChange(UUID(int=11), 90_000, Period(2026, 11), CREATED)
    fixed = RentChange(UUID(int=12), 85_000, Period(2026, 11), datetime(2026, 9, 2, tzinfo=UTC))
    changes = (FIRST_RENT, raised, fixed)

    assert rent_for(Period(2026, 10), changes) == 80_000
    assert rent_for(Period(2026, 11), changes) == 85_000
    assert rent_for(Period(2027, 3), changes) == 85_000


def test_before_the_first_rent_its_latest_correction_applies() -> None:
    corrected = RentChange(
        UUID(int=13), 70_000, FIRST_RENT.effective_period, datetime(2026, 9, 3, tzinfo=UTC)
    )

    assert rent_for(Period(2026, 1), (FIRST_RENT, corrected)) == 70_000


def test_missing_charges_run_from_the_control_month_to_today() -> None:
    charges = missing_rent_charges(lease(charged=frozenset({Period(2026, 9)})), date(2026, 11, 2))

    assert [(str(c.period), c.amount_cents, c.due_date) for c in charges] == [
        ("2026-10", 80_000, date(2026, 10, 5)),
        ("2026-11", 80_000, date(2026, 11, 5)),
    ]


@pytest.mark.parametrize(
    ("ends_on", "periods"),
    [
        (date(2026, 10, 1), ["2026-09", "2026-10"]),
        (date(2026, 9, 30), ["2026-09"]),
        (date(2026, 8, 31), []),
    ],
)
def test_the_month_holding_the_end_is_charged_in_full(ends_on: date, periods: list[str]) -> None:
    charges = missing_rent_charges(lease(ends_on=ends_on), date(2026, 12, 15))

    assert [str(charge.period) for charge in charges] == periods


def test_a_lease_starting_next_month_has_nothing_to_charge_yet() -> None:
    future = lease(start_date=date(2026, 11, 3), control_from=Period(2026, 11))

    assert missing_rent_charges(future, date(2026, 10, 27)) == []


@given(
    months=st.integers(min_value=0, max_value=30),
    charged=st.sets(st.integers(min_value=0, max_value=30)),
    end_after=st.one_of(st.none(), st.integers(min_value=0, max_value=30)),
)
def test_charging_the_missing_periods_leaves_none_missing(
    months: int, charged: set[int], end_after: int | None
) -> None:
    def nth(offset: int) -> Period:
        period = Period(2026, 1)
        for _ in range(offset):
            period = period.next()
        return period

    start = lease(
        control_from=Period(2026, 1),
        start_date=date(2026, 1, 1),
        rent_changes=(RentChange(UUID(int=10), 50_000, Period(2026, 1), CREATED),),
        charged=frozenset(nth(offset) for offset in charged),
        ends_on=None if end_after is None else nth(end_after).first_day(),
    )
    today = nth(months).last_day()
    missing = missing_rent_charges(start, today)
    last = months if end_after is None else min(months, end_after)

    assert {charge.period for charge in missing} | {
        nth(offset) for offset in charged if offset <= last
    } == {nth(offset) for offset in range(last + 1)}
    after = LeaseToCharge(
        **{**vars(start), "charged": start.charged | {charge.period for charge in missing}}
    )
    assert missing_rent_charges(after, today) == []
