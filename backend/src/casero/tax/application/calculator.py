from dataclasses import dataclass
from datetime import date
from typing import Literal, Protocol

from casero.tax.domain.assessment import Assessment, assess
from casero.tax.domain.rules import RucGroup, TaxRules


class TaxRuleBook(Protocol):
    async def rules_for(self, year: int) -> TaxRules | None: ...

    async def due_date(self, period: str, group: RucGroup) -> date | None: ...


class CalculatorRateLimiter(Protocol):
    async def allow(self, client: str) -> bool: ...


@dataclass(frozen=True)
class Calculation:
    period: str
    rules: TaxRules
    lines: list[Assessment]
    total_tax_cents: int
    due_on: date | None


CalculationOutcome = Calculation | Literal["limited", "unknown_year"]


def period_year(period: str) -> int:
    return int(period.split("-", 1)[0])


@dataclass(frozen=True)
class CalculateTax:
    """Public calculator: one line per renter for one month; nothing is stored."""

    rule_book: TaxRuleBook
    limiter: CalculatorRateLimiter

    async def __call__(
        self, period: str, collected: list[int], group: RucGroup | None, client: str
    ) -> CalculationOutcome:
        if not await self.limiter.allow(client):
            return "limited"
        rules = await self.rule_book.rules_for(period_year(period))
        if rules is None:
            return "unknown_year"
        lines = [assess(amount, rules) for amount in collected]
        due_on = await self.rule_book.due_date(period, group) if group else None
        return Calculation(
            period=period,
            rules=rules,
            lines=lines,
            total_tax_cents=sum(line.tax_cents for line in lines),
            due_on=due_on,
        )
