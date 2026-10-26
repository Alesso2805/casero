from dataclasses import dataclass

from casero.shared.kernel.money import BASIS_POINTS, round_half_up_to_sol
from casero.tax.domain.rules import TaxRules


@dataclass(frozen=True)
class Assessment:
    collected_cents: int
    base_cents: int
    tax_cents: int


def assess(collected_cents: int, rules: TaxRules) -> Assessment:
    """Tax of one declaration from what was collected from one renter in one month.

    The base and then the tax are rounded to whole soles, half up (SPEC; pending the
    accountant's confirmation, docs/ops/tax-config.md). Rates come from `tax_rule_sets`.
    """
    match rules.rounding:
        case "half_up_sol":
            base = round_half_up_to_sol(collected_cents)
            net_share_bp = BASIS_POINTS - rules.deduction_bp
            tax = round_half_up_to_sol(
                base * net_share_bp * rules.rate_bp, BASIS_POINTS * BASIS_POINTS
            )
    return Assessment(collected_cents=collected_cents, base_cents=base, tax_cents=tax)
