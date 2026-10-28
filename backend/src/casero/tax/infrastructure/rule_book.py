from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from casero.tax.application.calculator import period_year
from casero.tax.domain.rules import RucGroup, TaxRules

RULES = text(
    "SELECT year, rate_bp, deduction_bp, rounding, cash_threshold_cents, min_rent_bp, uit_cents"
    " FROM tax_rule_sets WHERE year = :year"
)
DUE_DATE = text(
    "SELECT due_date FROM sunat_due_dates"
    " WHERE period = :period AND ruc_group = :ruc_group AND year = :year"
)


class SqlTaxRuleBook:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def rules_for(self, year: int) -> TaxRules | None:
        row = (await self._connection.execute(RULES, {"year": year})).mappings().first()
        return TaxRules(**row) if row else None

    async def cash_threshold_for(self, year: int) -> int | None:
        rules = await self.rules_for(year)
        return None if rules is None else rules.cash_threshold_cents

    async def due_date(self, period: str, group: RucGroup) -> date | None:
        result = await self._connection.execute(
            DUE_DATE, {"period": period, "ruc_group": group, "year": period_year(period)}
        )
        due: date | None = result.scalar_one_or_none()
        return due
