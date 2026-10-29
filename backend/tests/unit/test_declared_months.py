from datetime import UTC, date, datetime
from uuid import UUID, uuid7

from casero.ledger.application.declared import months_a_void_changes, taxed_by_month
from casero.ledger.domain.allocation import Charge, Payment
from casero.shared.kernel.periods import Period

AT = datetime(2026, 10, 1, 15, 0, tzinfo=UTC)


def rent(cents: int, period: Period) -> Charge:
    return Charge(uuid7(), "rent", cents, period.first_day(), None, AT, period=period)


def old_debt(cents: int) -> Charge:
    return Charge(uuid7(), "opening_balance", cents, date(2025, 12, 31), True, AT)


def credit(cents: int, on: datetime) -> Charge:
    return Charge(uuid7(), "adjustment", -cents, on.date(), None, on)


def paid(cents: int, on: date) -> Payment:
    return Payment(uuid7(), cents, on, AT)


def changed(charges: list[Charge], payments: list[Payment], voided: UUID) -> list[Period]:
    if any(c.id == voided for c in charges):
        return months_a_void_changes(charges, payments, charge_id=voided)
    return months_a_void_changes(charges, payments, payment_id=voided)


SEPTEMBER, OCTOBER = Period(2026, 9), Period(2026, 10)


def test_voiding_a_payment_changes_its_month() -> None:
    september = paid(80_000, date(2026, 9, 5))
    october = paid(80_000, date(2026, 10, 5))
    charges = [rent(80_000, SEPTEMBER), rent(80_000, OCTOBER)]

    assert changed(charges, [september, october], september.id) == [SEPTEMBER]


def test_voiding_a_payment_of_the_old_debt_moves_it_to_the_next_payment() -> None:
    debt = old_debt(50_000)
    september = paid(50_000, date(2026, 9, 5))
    october = paid(80_000, date(2026, 10, 5))
    charges = [debt, rent(80_000, OCTOBER)]

    assert taxed_by_month(charges, [september, october]) == {SEPTEMBER: 0, OCTOBER: 80_000}
    assert changed(charges, [september, october], september.id) == [OCTOBER]


def test_voiding_the_old_debt_taxes_what_paid_it() -> None:
    debt = old_debt(50_000)
    september = paid(50_000, date(2026, 9, 5))
    october = paid(80_000, date(2026, 10, 5))

    assert changed([debt, rent(80_000, OCTOBER)], [september, october], debt.id) == [SEPTEMBER]


def test_voiding_a_credit_can_move_the_old_debt_to_a_later_payment() -> None:
    debt = old_debt(50_000)
    waived = credit(50_000, datetime(2026, 9, 1, 15, 0, tzinfo=UTC))
    october = paid(50_000, date(2026, 10, 5))

    assert changed([debt, waived], [october], waived.id) == [OCTOBER]


def test_voiding_a_rent_changes_no_taxed_month() -> None:
    september = rent(80_000, SEPTEMBER)
    payment = paid(80_000, date(2026, 9, 5))

    assert changed([september, rent(80_000, OCTOBER)], [payment], september.id) == []


def test_the_answer_is_the_same_once_voided() -> None:
    september = paid(80_000, date(2026, 9, 5))
    voided = Payment(september.id, 80_000, september.received_on, AT, voided=True)

    assert changed([rent(80_000, SEPTEMBER)], [voided], september.id) == [SEPTEMBER]
