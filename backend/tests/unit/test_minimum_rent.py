from casero.shared.kernel.periods import Period
from casero.tax.domain.minimum_rent import RentedProperty, below_minimum_rent
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
AUTOVALUO = 20_000_000


def months(*rents: int) -> dict[Period, int]:
    return {Period(2026, n): cents for n, cents in enumerate(rents, start=1)}


def test_a_rent_under_six_percent_of_the_autovaluo_is_flagged() -> None:
    under = RentedProperty(AUTOVALUO, 100, months(99_999, 99_999, 99_999))
    exact = RentedProperty(AUTOVALUO, 100, months(100_000, 100_000, 100_000))

    assert below_minimum_rent(under, RULES)
    assert not below_minimum_rent(exact, RULES)


def test_the_floor_is_prorated_by_the_part_rented() -> None:
    a_quarter = RentedProperty(AUTOVALUO, 25, months(25_000))

    assert not below_minimum_rent(a_quarter, RULES)
    assert below_minimum_rent(RentedProperty(AUTOVALUO, 26, months(25_000)), RULES)


def test_the_floor_counts_only_the_months_rented() -> None:
    two_rooms_in_one_month = RentedProperty(AUTOVALUO, 100, {Period(2026, 3): 60_000 + 40_000})

    assert not below_minimum_rent(two_rooms_in_one_month, RULES)
    assert not below_minimum_rent(RentedProperty(AUTOVALUO, 100, {}), RULES)
