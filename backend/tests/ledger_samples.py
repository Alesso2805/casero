from datetime import UTC, date, datetime
from uuid import UUID

from hypothesis import strategies as st

from casero.ledger.domain.allocation import Charge, ChargeKind, Payment

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
