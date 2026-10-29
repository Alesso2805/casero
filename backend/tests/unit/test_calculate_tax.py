from datetime import date

import pytest

from casero.shared.kernel.periods import Period
from casero.tax.application.calculator import CalculateTax, Calculation
from casero.tax.domain.rules import RucGroup, TaxRules

pytestmark = pytest.mark.anyio

MARCH = Period(2026, 3)

RULES = TaxRules(
    year=2026,
    rate_bp=625,
    deduction_bp=2000,
    rounding="half_up_sol",
    cash_threshold_cents=200000,
    min_rent_bp=600,
    uit_cents=550000,
)


class RuleBook:
    def __init__(self) -> None:
        self.due_lookups: list[tuple[Period, RucGroup]] = []

    async def rules_for(self, year: int) -> TaxRules | None:
        return RULES if year == 2026 else None

    async def due_date(self, period: Period, group: RucGroup) -> date | None:
        self.due_lookups.append((period, group))
        return date(2026, 4, 17)


class Limiter:
    def __init__(self, allowed: bool = True) -> None:
        self.allowed = allowed

    async def allow(self, client: str) -> bool:
        return self.allowed


async def test_each_line_is_one_declaration_and_the_total_adds_their_taxes() -> None:
    calculate = CalculateTax(RuleBook(), Limiter())

    outcome = await calculate(MARCH, [55100, 54950, 0], "0", "203.0.113.7")

    assert isinstance(outcome, Calculation)
    assert [line.tax_cents for line in outcome.lines] == [2800, 2800, 0]
    assert outcome.total_tax_cents == 5600
    assert outcome.due_on == date(2026, 4, 17)


async def test_the_due_date_is_looked_up_only_with_a_ruc_group() -> None:
    rule_book = RuleBook()

    outcome = await CalculateTax(rule_book, Limiter())(MARCH, [10000], None, "203.0.113.7")

    assert isinstance(outcome, Calculation)
    assert outcome.due_on is None
    assert rule_book.due_lookups == []


async def test_a_year_without_rules_and_a_limited_client_get_no_calculation() -> None:
    december = Period(2025, 12)

    assert await CalculateTax(RuleBook(), Limiter())(december, [100], None, "x") == "unknown_year"
    assert await CalculateTax(RuleBook(), Limiter(False))(MARCH, [100], None, "x") == "limited"
