from datetime import UTC, date, datetime
from random import Random
from uuid import UUID

from hypothesis import given
from hypothesis import strategies as st

from casero.ledger.domain.allocation import (
    Charge,
    ChargeKind,
    Payment,
    allocate,
    charge_status,
    movements,
)

LIMA_NOON = 17  # 12:00 in Lima is 17:00 UTC.


def at(day: date, minute: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, LIMA_NOON, minute, tzinfo=UTC)


def rent(n: int, cents: int, due: date) -> Charge:
    return Charge(UUID(int=n), "rent", cents, due, None, at(due.replace(day=1), n))


def opening(n: int, cents: int, pre_2026: bool, due: date) -> Charge:
    return Charge(UUID(int=n), "opening_balance", cents, due, pre_2026, at(date(2026, 9, 1), n))


def credit(n: int, cents: int, on: date) -> Charge:
    return Charge(UUID(int=n), "adjustment", -cents, on, None, at(on, n))


def payment(n: int, cents: int, on: date, minute: int = 0) -> Payment:
    return Payment(UUID(int=n), cents, on, at(on, minute))


SEPT = rent(1, 80_000, date(2026, 9, 5))
OCT = rent(2, 80_000, date(2026, 10, 5))


def test_a_partial_payment_leaves_the_rest_of_the_oldest_charge_pending() -> None:
    result = allocate([SEPT, OCT], [payment(10, 50_000, date(2026, 9, 6))])

    assert result.outstanding == {SEPT.id: 30_000, OCT.id: 80_000}
    assert result.balance_cents == 110_000


def test_an_advance_payment_covers_later_charges_and_keeps_the_rest_in_favor() -> None:
    result = allocate([SEPT, OCT], [payment(10, 200_000, date(2026, 9, 1))])

    assert result.outstanding == {SEPT.id: 0, OCT.id: 0}
    assert result.unapplied_cents == 40_000
    assert result.balance_cents == -40_000


def test_debt_from_2025_or_before_is_paid_first_then_2026_then_by_due_date() -> None:
    old = opening(3, 120_000, True, date(2025, 12, 31))
    recent = opening(4, 50_000, False, date(2026, 8, 31))
    pay = payment(10, 150_000, date(2026, 9, 10))

    result = allocate([SEPT, recent, old], [pay])

    assert result.covered_by(pay.id) == {old.id: 120_000, recent.id: 30_000}


def test_on_the_same_day_payments_go_before_credits() -> None:
    day = date(2026, 9, 10)
    late_payment = payment(10, 30_000, day, minute=59)
    early_credit = credit(5, 80_000, day)

    result = allocate([SEPT, OCT, early_credit], [late_payment])

    assert result.covered_by(late_payment.id) == {SEPT.id: 30_000}
    assert result.covered_by(early_credit.id) == {SEPT.id: 50_000, OCT.id: 30_000}


def test_a_credit_is_never_money_received_and_voided_records_count_for_nothing() -> None:
    voided_rent = Charge(
        UUID(int=6), "rent", 99_000, date(2026, 8, 5), None, at(date(2026, 8, 1)), True
    )
    voided_payment = Payment(UUID(int=11), 99_000, date(2026, 9, 1), at(date(2026, 9, 1)), True)

    result = allocate([SEPT, voided_rent, credit(5, 20_000, date(2026, 9, 2))], [voided_payment])

    assert result.outstanding == {SEPT.id: 60_000}
    assert result.balance_cents == 60_000


def test_a_credit_takes_effect_on_the_lima_date_it_was_recorded() -> None:
    late_night = Charge(
        UUID(int=7),
        "adjustment",
        -1_000,
        date(2026, 9, 30),
        None,
        datetime(2026, 10, 1, 3, 0, tzinfo=UTC),
    )

    [move] = movements([late_night], [])

    assert move.effective_on == date(2026, 9, 30)


def test_statuses_follow_their_precedence() -> None:
    due = date(2026, 10, 5)

    assert charge_status(due, 0, date(2026, 10, 9)) == "paid"
    assert charge_status(due, 1, date(2026, 10, 6)) == "overdue"
    assert charge_status(due, 1, due) == "due_today"
    assert charge_status(due, 1, date(2026, 10, 2)) == "due_soon"
    assert charge_status(due, 1, date(2026, 10, 1)) == "pending"


DAYS = st.dates(min_value=date(2026, 1, 1), max_value=date(2026, 3, 31))
CENTS = st.integers(min_value=1, max_value=500_000)
KINDS: list[ChargeKind] = ["rent", "rent_correction", "opening_balance", "adjustment"]


@st.composite
def ledgers(draw: st.DrawFn) -> tuple[list[Charge], list[Payment]]:
    charges: list[Charge] = []
    for n in range(draw(st.integers(min_value=0, max_value=8))):
        kind = draw(st.sampled_from(KINDS))
        amount = draw(CENTS)
        if kind == "adjustment" and draw(st.booleans()):
            amount = -amount
        day = draw(DAYS)
        charges.append(
            Charge(
                UUID(int=100 + n),
                kind,
                amount,
                day,
                draw(st.booleans()) if kind == "opening_balance" else None,
                at(day, draw(st.integers(min_value=0, max_value=59))),
                draw(st.booleans()),
            )
        )
    payments = [
        Payment(
            UUID(int=500 + n),
            draw(CENTS),
            day := draw(DAYS),
            at(day, draw(st.integers(min_value=0, max_value=59))),
            draw(st.booleans()),
        )
        for n in range(draw(st.integers(min_value=0, max_value=8)))
    ]
    return charges, payments


@given(ledgers())
def test_the_balance_is_valid_charges_minus_valid_payments(
    ledger: tuple[list[Charge], list[Payment]],
) -> None:
    charges, payments = ledger
    result = allocate(charges, payments)

    expected = sum(c.amount_cents for c in charges if not c.voided) - sum(
        p.amount_cents for p in payments if not p.voided
    )
    assert result.balance_cents == expected
    assert all(cents >= 0 for cents in result.outstanding.values())
    assert sum(result.outstanding.values()) - result.unapplied_cents == expected


@given(ledgers(), st.randoms())
def test_insertion_order_within_a_day_does_not_change_any_charge(
    ledger: tuple[list[Charge], list[Payment]], random: Random
) -> None:
    charges, payments = ledger
    by_day: dict[date, list[datetime]] = {}
    for p in payments:
        by_day.setdefault(p.received_on, []).append(p.created_at)
    for stamps in by_day.values():
        random.shuffle(stamps)
    shuffled = [
        Payment(p.id, p.amount_cents, p.received_on, by_day[p.received_on].pop(), p.voided)
        for p in payments
    ]

    assert allocate(charges, shuffled).outstanding == allocate(charges, payments).outstanding


@given(ledgers(), CENTS)
def test_a_later_movement_never_changes_how_earlier_ones_were_applied(
    ledger: tuple[list[Charge], list[Payment]], cents: int
) -> None:
    charges, payments = ledger
    later = Payment(UUID(int=999), cents, date(2026, 4, 1), at(date(2026, 4, 1)))

    before = allocate(charges, payments).covered
    after = allocate(charges, [*payments, later]).covered

    assert {key: value for key, value in after.items() if key[0] != later.id} == before


@given(ledgers(), CENTS)
def test_a_later_credit_never_changes_how_earlier_payments_were_applied(
    ledger: tuple[list[Charge], list[Payment]], cents: int
) -> None:
    charges, payments = ledger
    late_credit = Charge(
        UUID(int=998), "adjustment", -cents, date(2026, 4, 2), None, at(date(2026, 4, 2))
    )

    before = allocate(charges, payments).covered
    after = allocate([*charges, late_credit], payments).covered

    assert {key: value for key, value in after.items() if key[0] != late_credit.id} == before
