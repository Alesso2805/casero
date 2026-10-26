from dataclasses import dataclass
from typing import Literal

RoundingMethod = Literal["half_up_sol"]
RucGroup = Literal["0", "1", "2-3", "4-5", "6-7", "8-9", "bc"]
RUC_GROUPS: tuple[RucGroup, ...] = ("0", "1", "2-3", "4-5", "6-7", "8-9", "bc")
ROUNDING_METHODS: tuple[RoundingMethod, ...] = ("half_up_sol",)


@dataclass(frozen=True)
class TaxRules:
    year: int
    rate_bp: int
    deduction_bp: int
    rounding: RoundingMethod
    cash_threshold_cents: int
    min_rent_bp: int
    uit_cents: int
