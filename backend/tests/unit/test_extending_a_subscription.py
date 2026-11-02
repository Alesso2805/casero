from datetime import date

import pytest
from hypothesis import given
from hypothesis import strategies as st

from casero.accounts.domain.entitlements import Subscription, extended_until, is_paid_month
from casero.shared.kernel.periods import Period, add_months


def subscription(ends_at: date | None, trial_ends_at: date | None = None) -> Subscription:
    return Subscription("casero", date(2026, 1, 1), trial_ends_at, ends_at, None)


@pytest.mark.parametrize(
    ("day", "months", "expected"),
    [
        (date(2026, 3, 15), 1, date(2026, 4, 15)),
        (date(2026, 1, 31), 1, date(2026, 2, 28)),
        (date(2028, 1, 31), 1, date(2028, 2, 29)),
        (date(2026, 12, 31), 1, date(2027, 1, 31)),
        (date(2026, 11, 30), 3, date(2027, 2, 28)),
        (date(2026, 2, 28), 12, date(2027, 2, 28)),
        (date(2026, 6, 15), 24, date(2028, 6, 15)),
    ],
)
def test_adding_months_stays_on_the_day_or_on_the_last_one(
    day: date, months: int, expected: date
) -> None:
    assert add_months(day, months) == expected


@given(
    day=st.dates(min_value=date(2026, 1, 1), max_value=date(2040, 12, 31)),
    months=st.integers(min_value=1, max_value=24),
)
def test_adding_months_lands_that_many_calendar_months_later(day: date, months: int) -> None:
    moved = add_months(day, months)

    assert (moved.year * 12 + moved.month) - (day.year * 12 + day.month) == months
    assert moved.day <= day.day


def test_paying_during_the_trial_keeps_the_days_left_in_it() -> None:
    trial = subscription(date(2026, 11, 26), date(2026, 11, 26))

    assert extended_until(trial, 1, date(2026, 11, 10)) == date(2026, 12, 26)


def test_paying_while_active_continues_from_the_end_of_what_was_paid() -> None:
    assert extended_until(subscription(date(2026, 12, 15)), 12, date(2026, 12, 1)) == date(
        2027, 12, 15
    )


def test_paying_during_the_grace_days_leaves_no_gap_and_no_free_days() -> None:
    assert extended_until(subscription(date(2026, 11, 2)), 1, date(2026, 11, 8)) == date(
        2026, 12, 2
    )


def test_paying_on_the_first_day_after_the_grace_starts_that_day() -> None:
    assert extended_until(subscription(date(2026, 11, 2)), 1, date(2026, 11, 9)) == date(
        2026, 12, 9
    )


def test_a_payment_long_after_it_lapsed_starts_the_day_it_was_paid() -> None:
    assert extended_until(subscription(date(2026, 3, 1)), 3, date(2026, 10, 20)) == date(
        2027, 1, 20
    )


def test_the_day_it_was_paid_decides_however_late_it_is_recorded() -> None:
    lapsed_since_march = subscription(date(2026, 3, 1))

    paid_in_grace = extended_until(lapsed_since_march, 1, date(2026, 3, 5))

    assert paid_in_grace == date(2026, 4, 1)


def test_a_subscription_without_an_end_gets_one_from_the_day_it_was_paid() -> None:
    assert extended_until(subscription(None), 1, date(2026, 11, 1)) == date(2026, 12, 1)


def test_a_paid_trial_makes_the_months_after_it_count_as_paid_and_never_its_own() -> None:
    trial = subscription(date(2026, 11, 26), date(2026, 11, 26))

    ends_at = extended_until(trial, 2, date(2026, 11, 10))
    paid = Subscription("casero", date(2026, 1, 1), date(2026, 11, 26), ends_at, None)

    assert ends_at == date(2027, 1, 26)
    assert not is_paid_month(paid, Period(2026, 11))
    assert is_paid_month(paid, Period(2026, 12))
    assert is_paid_month(paid, Period(2027, 1))
    assert not is_paid_month(paid, Period(2027, 2))
