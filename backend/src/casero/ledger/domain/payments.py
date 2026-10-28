from datetime import date
from typing import Literal

from casero.shared.kernel.periods import FIRST_CONTROL_PERIOD, Period

PaymentMethod = Literal["cash", "yape", "plin", "transfer", "bank_deposit"]
ReceiptProblem = Literal["received_in_future", "received_before_control"]


def earliest_receipt(control_from: Period, has_opening_balance: bool) -> date:
    """A lease with prior debt may have collected it since 2026 began (SPEC, "Fecha de cobro")."""
    start = FIRST_CONTROL_PERIOD if has_opening_balance else control_from
    return start.first_day()


def receipt_problem(
    received_on: date, today: date, control_from: Period, has_opening_balance: bool
) -> ReceiptProblem | None:
    if received_on > today:
        return "received_in_future"
    if received_on < earliest_receipt(control_from, has_opening_balance):
        return "received_before_control"
    return None


def needs_bank(method: PaymentMethod, rent_cents: int, threshold_cents: int | None) -> bool:
    """Cash for a rent at or above the year's threshold must go through a bank (SPEC)."""
    return method == "cash" and threshold_cents is not None and rent_cents >= threshold_cents
