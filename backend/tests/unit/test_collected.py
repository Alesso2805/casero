from collections import Counter
from dataclasses import replace
from datetime import date, datetime
from random import Random
from uuid import UUID

from hypothesis import given
from hypothesis import strategies as st

from casero.ledger.application.collected import collected_payments, rents_charged
from casero.ledger.application.collections import LeaseBook
from casero.ledger.domain.allocation import Charge, Payment, allocate, paid_toward_old_debt
from casero.shared.kernel.periods import Period
from ledger_samples import credit, ledgers, opening, payment, rent

OLD_DEBT = opening(3, 120_000, True, date(2025, 12, 31))
DEBT_2026 = opening(4, 40_000, False, date(2026, 8, 31))
SEPT = rent(1, 80_000, date(2026, 9, 5))


def test_collecting_debt_from_2025_is_set_apart_and_2026_debt_is_not() -> None:
    pay = payment(10, 180_000, date(2026, 10, 10))

    old = paid_toward_old_debt(allocate([SEPT, DEBT_2026, OLD_DEBT], [pay]), [OLD_DEBT, SEPT])

    assert old == {pay.id: 120_000}


def test_a_credit_on_the_old_debt_leaves_less_of_it_for_the_payments() -> None:
    discount = credit(5, 20_000, date(2026, 9, 2))
    pay = payment(10, 150_000, date(2026, 10, 10))
    charges = [OLD_DEBT, SEPT, discount]

    old = paid_toward_old_debt(allocate(charges, [pay]), charges)

    assert old == {pay.id: 100_000}


def test_the_months_payments_carry_their_taxable_part() -> None:
    september_pay = payment(10, 50_000, date(2026, 9, 6))
    october_pay = payment(11, 150_000, date(2026, 10, 10))
    voided = replace(payment(12, 9_000, date(2026, 10, 12)), voided=True)
    lease = LeaseBook(UUID(int=100), False, [OLD_DEBT, SEPT], [september_pay, october_pay, voided])

    october = collected_payments([lease], Period(2026, 10))

    assert [(p.payment_id, p.old_debt_cents, p.taxable_cents) for p in october] == [
        (october_pay.id, 70_000, 80_000)
    ]


def test_each_month_has_the_valid_rent_or_the_correction_that_replaced_it() -> None:
    august = replace(rent(1, 70_000, date(2026, 8, 5)), period=Period(2026, 8))
    september = replace(rent(2, 80_000, date(2026, 9, 5)), period=Period(2026, 9), voided=True)
    corrected = replace(
        september, id=UUID(int=5), kind="rent_correction", amount_cents=75_000, voided=False
    )
    october = replace(rent(6, 80_000, date(2026, 10, 5)), period=Period(2026, 10))
    lease = LeaseBook(UUID(int=100), False, [OLD_DEBT, august, september, corrected, october], [])

    rents = rents_charged([lease], Period(2026, 9), Period(2026, 10))

    assert rents == {UUID(int=100): {Period(2026, 9): 75_000, Period(2026, 10): 80_000}}


@given(ledgers(), st.randoms())
def test_the_old_debt_paid_each_month_does_not_depend_on_entry_order(
    ledger: tuple[list[Charge], list[Payment]], random: Random
) -> None:
    charges, payments = ledger
    by_day: dict[date, list[datetime]] = {}
    for p in payments:
        by_day.setdefault(p.received_on, []).append(p.created_at)
    for stamps in by_day.values():
        random.shuffle(stamps)
    shuffled = [replace(p, created_at=by_day[p.received_on].pop()) for p in payments]

    def per_month(movements: list[Payment]) -> Counter[Period]:
        old = paid_toward_old_debt(allocate(charges, movements), charges)
        months: Counter[Period] = Counter()
        for p in movements:
            months[Period.of(p.received_on)] += old.get(p.id, 0)
            assert 0 <= old.get(p.id, 0) <= p.amount_cents
        return months

    assert per_month(shuffled) == per_month(payments)
