from datetime import date

import pytest

from casero.ledger.domain.payments import before_control, receipt_problem
from casero.shared.kernel.periods import Period

TODAY = date(2026, 10, 28)


@pytest.mark.parametrize(
    ("received_on", "problem"),
    [
        (date(2026, 10, 29), "received_in_future"),
        (date(2025, 12, 31), "received_before_2026"),
        (date(2026, 1, 1), None),
        (TODAY, None),
    ],
)
def test_a_receipt_is_dated_from_2026_up_to_today(received_on: date, problem: str | None) -> None:
    assert receipt_problem(received_on, TODAY) == problem


def test_rent_paid_at_signing_is_flagged_as_before_the_control_month() -> None:
    november = Period(2026, 11)

    assert before_control(date(2026, 10, 28), november)
    assert not before_control(date(2026, 11, 1), november)
