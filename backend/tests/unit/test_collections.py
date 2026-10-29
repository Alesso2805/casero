from datetime import date, datetime
from uuid import UUID

import pytest
from hypothesis import given
from hypothesis import strategies as st

from casero.ledger.application.collections import GetCollections, LeaseBook
from casero.ledger.domain.allocation import Charge, Payment
from casero.ledger.domain.collections import collection
from ledger_samples import at, credit, ledgers, opening, payment, rent

TODAY = date(2026, 10, 27)
SEPT = rent(1, 80_000, date(2026, 9, 5))
OCT = rent(2, 80_000, date(2026, 10, 29))
NOV = rent(3, 80_000, date(2026, 11, 5))


class Clock:
    def now(self) -> datetime:
        return at(TODAY)

    def today_lima(self) -> date:
        return TODAY


class Books:
    def __init__(self, books: list[LeaseBook]) -> None:
        self._books = books

    async def lease_books(self) -> list[LeaseBook]:
        return self._books


def test_an_overdue_lease_shows_its_days_amount_and_next_charge() -> None:
    result = collection([SEPT, OCT, NOV], [payment(10, 50_000, date(2026, 9, 6))], TODAY)

    assert result.status == "overdue"
    assert (result.overdue_days, result.overdue_cents) == (52, 30_000)
    assert (result.next_due_on, result.next_due_cents) == (date(2026, 10, 29), 80_000)
    assert result.due_by_month_end_cents == 110_000
    assert result.balance_cents == 190_000


def test_prior_debt_is_already_overdue() -> None:
    result = collection([opening(4, 120_000, True, date(2025, 12, 31))], [], TODAY)

    assert (result.status, result.overdue_days, result.overdue_cents) == ("overdue", 300, 120_000)


@pytest.mark.parametrize(
    ("due", "status"),
    [
        (TODAY, "due_today"),
        (date(2026, 10, 30), "due_soon"),
        (date(2026, 10, 31), "up_to_date"),
    ],
)
def test_without_overdue_charges_the_next_one_sets_the_status(due: date, status: str) -> None:
    result = collection([rent(1, 80_000, due)], [], TODAY)

    assert result.status == status
    assert (result.next_due_on, result.overdue_cents) == (due, 0)


def test_money_in_favor_leaves_nothing_to_collect() -> None:
    result = collection(
        [SEPT, credit(5, 10_000, date(2026, 9, 2))], [payment(10, 90_000, TODAY)], TODAY
    )

    assert result.status == "up_to_date"
    assert (result.next_due_on, result.due_by_month_end_cents) == (None, 0)
    assert result.balance_cents == -20_000


@pytest.mark.anyio
async def test_the_most_urgent_go_first_and_ended_leases_only_while_they_owe() -> None:
    def book(n: int, charges: list[Charge], ended: bool = False) -> LeaseBook:
        return LeaseBook(UUID(int=n), ended, charges, [])

    later = book(1, [NOV])
    soon = book(2, [rent(11, 80_000, date(2026, 10, 29))])
    today = book(3, [rent(12, 50_000, TODAY)])
    recent = book(4, [rent(13, 80_000, date(2026, 10, 20))])
    oldest = book(5, [SEPT], ended=True)
    settled = book(6, [], ended=True)

    result = await GetCollections(Books([later, soon, today, recent, oldest, settled]), Clock())()

    assert [line.lease_id for line in result.leases] == [
        oldest.lease_id,
        recent.lease_id,
        today.lease_id,
        soon.lease_id,
        later.lease_id,
    ]
    assert result.leases[0].ended is True
    assert result.overdue_cents == 160_000
    assert result.due_by_month_end_cents == 290_000


@given(ledgers(), st.dates(min_value=date(2026, 1, 1), max_value=date(2026, 4, 30)))
def test_what_is_due_never_exceeds_what_is_owed(
    ledger: tuple[list[Charge], list[Payment]], today: date
) -> None:
    charges, payments = ledger
    result = collection(charges, payments, today)

    assert 0 <= result.overdue_cents <= result.due_by_month_end_cents
    assert result.due_by_month_end_cents <= max(result.balance_cents, 0)
    assert (result.status == "overdue") == (result.overdue_cents > 0)
    assert (result.next_due_on is None) == (result.next_due_cents == 0)


def test_only_an_unpaid_rent_can_be_reminded_by_whatsapp() -> None:
    prior_debt = opening(1, 30_000, False, date(2026, 8, 31))
    october = rent(2, 80_000, date(2026, 10, 5))

    only_prior_debt = collection([prior_debt], [], TODAY)
    with_rent = collection([prior_debt, october], [], TODAY)
    paid = collection([october], [payment(10, 80_000, date(2026, 10, 5))], TODAY)

    assert only_prior_debt.status == "overdue"
    assert not only_prior_debt.rent_to_remind
    assert with_rent.rent_to_remind
    assert not paid.rent_to_remind
