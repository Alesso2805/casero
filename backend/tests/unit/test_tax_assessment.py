from fractions import Fraction

import pytest
from hypothesis import given
from hypothesis import strategies as st

from casero.shared.kernel.money import round_half_up_to_sol
from casero.tax.domain.assessment import assess
from casero.tax.domain.rules import TaxRules

RULES = TaxRules(
    year=2026,
    rate_bp=625,
    deduction_bp=2000,
    rounding="half_up_sol",
    cash_threshold_cents=200000,
    min_rent_bp=600,
    uit_cents=550000,
)
CENTS = st.integers(min_value=0, max_value=10**12)
HALF = Fraction(1, 2)


def exact_half_up_soles(amount_in_soles: Fraction) -> int:
    return int(amount_in_soles + HALF) * 100


@pytest.mark.parametrize(
    ("collected", "base", "tax"),
    [
        (45050 + 10050, 55100, 2800),
        (54950, 55000, 2800),
        (54949, 54900, 2700),
        (100000, 100000, 5000),
        (0, 0, 0),
        (149, 100, 0),
        (1000, 1000, 100),
    ],
)
def test_known_cases(collected: int, base: int, tax: int) -> None:
    assessment = assess(collected, RULES)

    assert (assessment.base_cents, assessment.tax_cents) == (base, tax)


@given(CENTS)
def test_the_base_is_what_was_collected_rounded_to_whole_soles(collected: int) -> None:
    base = assess(collected, RULES).base_cents

    assert base % 100 == 0
    assert base == exact_half_up_soles(Fraction(collected, 100))


@given(CENTS, st.integers(min_value=1, max_value=10_000), st.integers(min_value=0, max_value=9_999))
def test_the_tax_is_the_exact_rate_on_the_base_rounded_half_up(
    collected: int, rate_bp: int, deduction_bp: int
) -> None:
    rules = TaxRules(2026, rate_bp, deduction_bp, "half_up_sol", 1, 1, 1)
    assessment = assess(collected, rules)
    exact = (
        Fraction(assessment.base_cents, 100)
        * (1 - Fraction(deduction_bp, 10_000))
        * Fraction(rate_bp, 10_000)
    )

    assert assessment.tax_cents == exact_half_up_soles(exact)


@given(CENTS, CENTS)
def test_collecting_more_never_lowers_the_tax(first: int, second: int) -> None:
    low, high = sorted((first, second))

    assert assess(low, RULES).tax_cents <= assess(high, RULES).tax_cents


def test_negative_amounts_are_refused() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        round_half_up_to_sol(-1)
