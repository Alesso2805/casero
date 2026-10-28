from datetime import date
from typing import Literal

from casero.shared.kernel.periods import FIRST_CONTROL_PERIOD, Period

PaymentMethod = Literal["cash", "yape", "plin", "transfer", "bank_deposit"]
ReceiptProblem = Literal["received_in_future", "received_before_2026"]


def receipt_problem(received_on: date, today: date) -> ReceiptProblem | None:
    if received_on > today:
        return "received_in_future"
    if received_on < FIRST_CONTROL_PERIOD.first_day():
        return "received_before_2026"
    return None


def before_control(received_on: date, control_from: Period) -> bool:
    """Accepted, with a warning: rent paid at signing counts in the month it was collected."""
    return received_on < control_from.first_day()


def needs_bank(method: PaymentMethod, rent_cents: int, threshold_cents: int | None) -> bool:
    """Cash for a rent at or above the year's threshold must go through a bank (SPEC)."""
    return method == "cash" and threshold_cents is not None and rent_cents >= threshold_cents
