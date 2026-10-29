from collections import Counter
from dataclasses import replace
from datetime import date, datetime
from random import Random
from uuid import UUID

from hypothesis import given
from hypothesis import strategies as st

from casero.ledger.domain.allocation import Charge, Payment, allocate, paid_toward_old_debt
from casero.shared.kernel.periods import Period
from casero.tax.domain.declarations import Declarant, TaxablePayment, declarations
from casero.tax.domain.rules import TaxRules
from ledger_samples import CENTS, at, credit, ledgers, opening, payment, rent

RULES = TaxRules(
    year=2026,
    rate_bp=625,
    deduction_bp=2000,
    rounding="half_up_sol",
    cash_threshold_cents=200000,
    min_rent_bp=600,
    uit_cents=550000,
)
OCTOBER = Period(2026, 10)
ANA = Declarant(b"ana-dni", UUID(int=1))
LUIS = Declarant(b"luis-dni", UUID(int=2))
ROSA_WITHOUT_DOCUMENT = Declarant(None, UUID(int=3))


def taxable(
    declarant: Declarant, lease: int, cents: int, on: date, old_debt: int = 0
) -> TaxablePayment:
    return TaxablePayment(declarant, UUID(int=lease), on, cents, old_debt)


def test_one_tenant_with_two_leases_files_one_declaration_with_both() -> None:
    [declaration] = declarations(
        [
            taxable(ANA, 10, 45_050, date(2026, 10, 5)),
            taxable(ANA, 11, 10_050, date(2026, 10, 20)),
        ],
        OCTOBER,
        RULES,
    )

    assert (declaration.base_cents, declaration.tax_cents) == (55_100, 2_800)
    assert declaration.lease_ids == (UUID(int=10), UUID(int=11))


def test_each_document_has_its_own_and_a_tenant_without_one_is_incomplete() -> None:
    result = declarations(
        [
            taxable(ANA, 10, 80_000, date(2026, 10, 5)),
            taxable(LUIS, 12, 60_000, date(2026, 10, 6)),
            taxable(ROSA_WITHOUT_DOCUMENT, 13, 50_000, date(2026, 10, 7)),
            taxable(ANA, 10, 80_000, date(2026, 9, 5)),
        ],
        OCTOBER,
        RULES,
    )

    assert [(d.declarant, d.collected_cents, d.incomplete) for d in result] == [
        (ANA, 80_000, False),
        (LUIS, 60_000, False),
        (ROSA_WITHOUT_DOCUMENT, 50_000, True),
    ]


def test_debt_from_2025_is_shown_apart_and_stays_out_of_the_base() -> None:
    [declaration] = declarations(
        [taxable(ANA, 10, 30_000, date(2026, 10, 10), old_debt=120_000)], OCTOBER, RULES
    )

    assert (declaration.collected_cents, declaration.old_debt_cents) == (30_000, 120_000)
    assert (declaration.base_cents, declaration.tax_cents) == (30_000, 1_500)


def monthly_taxes(charges: list[Charge], payments: list[Payment]) -> Counter[Period]:
    """One lease, one tenant: the tax of each month the way the app computes it."""
    old_debt = paid_toward_old_debt(allocate(charges, payments), charges)
    collected = [
        taxable(
            ANA,
            10,
            p.amount_cents - old_debt.get(p.id, 0),
            p.received_on,
            old_debt.get(p.id, 0),
        )
        for p in payments
        if not p.voided
    ]
    taxes: Counter[Period] = Counter()
    for month in {Period.of(p.received_on) for p in collected}:
        taxes[month] = sum(d.tax_cents for d in declarations(collected, month, RULES))
    return taxes


def test_a_credit_after_payments_on_2025_debt_changes_none_of_their_months() -> None:
    old = opening(3, 120_000, True, date(2025, 12, 31))
    september, october = rent(1, 80_000, date(2026, 9, 5)), rent(2, 80_000, date(2026, 10, 5))
    payments = [payment(10, 150_000, date(2026, 9, 10)), payment(11, 80_000, date(2026, 10, 8))]
    late_credit = credit(5, 50_000, date(2026, 10, 20))

    before = monthly_taxes([old, september, october], payments)
    after = monthly_taxes([old, september, october, late_credit], payments)

    assert after == before == Counter({Period(2026, 9): 1_500, Period(2026, 10): 4_000})


@given(ledgers(), st.randoms())
def test_the_tax_does_not_depend_on_the_order_payments_were_entered_in_a_day(
    ledger: tuple[list[Charge], list[Payment]], random: Random
) -> None:
    charges, payments = ledger
    by_day: dict[date, list[datetime]] = {}
    for p in payments:
        by_day.setdefault(p.received_on, []).append(p.created_at)
    for stamps in by_day.values():
        random.shuffle(stamps)
    shuffled = [replace(p, created_at=by_day[p.received_on].pop()) for p in payments]

    assert monthly_taxes(charges, shuffled) == monthly_taxes(charges, payments)


@given(ledgers(), CENTS, st.dates(min_value=date(2026, 1, 1), max_value=date(2026, 4, 30)))
def test_a_credit_never_changes_the_tax_of_a_month_before_it(
    ledger: tuple[list[Charge], list[Payment]], cents: int, day: date
) -> None:
    charges, payments = ledger
    new_credit = Charge(UUID(int=997), "adjustment", -cents, day, None, at(day))

    before = monthly_taxes(charges, payments)
    after = monthly_taxes([*charges, new_credit], payments)

    month = Period.of(day)
    assert {m: tax for m, tax in after.items() if m < month} == {
        m: tax for m, tax in before.items() if m < month
    }
