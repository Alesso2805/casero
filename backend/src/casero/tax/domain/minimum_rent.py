from collections.abc import Mapping
from dataclasses import dataclass

from casero.shared.kernel.money import BASIS_POINTS, WHOLE_PERCENT
from casero.shared.kernel.periods import MONTHS_PER_YEAR, Period
from casero.tax.domain.rules import TaxRules


@dataclass(frozen=True)
class RentedProperty:
    autovaluo_cents: int
    rented_share_pct: int
    rent_by_period: Mapping[Period, int]


def below_minimum_rent(rented: RentedProperty, rules: TaxRules) -> bool:
    """The rent of the months rented is under the year's share of the autovalúo.

    LIR art. 23 a): the rent can't be under 6 % of the autovalúo, prorated by the part and
    the months rented; the difference is taxed in the annual return, so Casero only warns
    and never computes the amount (SPEC).
    """
    months = len(rented.rent_by_period)
    rent = sum(rented.rent_by_period.values())
    floor = rented.autovaluo_cents * rules.min_rent_bp * rented.rented_share_pct * months
    return months > 0 and rent * BASIS_POINTS * WHOLE_PERCENT * MONTHS_PER_YEAR < floor
