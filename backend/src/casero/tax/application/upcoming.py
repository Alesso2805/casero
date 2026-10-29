from dataclasses import dataclass
from datetime import date
from typing import Literal

from casero.accounts.application.profile import Profiles
from casero.shared.kernel.clock import Clock
from casero.shared.kernel.periods import Period
from casero.tax.application.calculator import TaxRuleBook
from casero.tax.application.declarations import GetDeclarations

NOTICE_DAYS = 5


@dataclass(frozen=True)
class UpcomingDue:
    period: Period
    due_on: date
    days_left: int
    pending_cents: int
    declarations: int


@dataclass(frozen=True)
class GetUpcomingDue:
    """The fixed notice in the app during the last days before a 1683 falls due (SPEC)."""

    declarations: GetDeclarations
    profiles: Profiles
    rule_book: TaxRuleBook
    clock: Clock

    async def __call__(self) -> UpcomingDue | Literal["tax_module_unavailable"] | None:
        group = (await self.profiles.current()).ruc_group
        if group is None:
            return None
        today = self.clock.today_lima()
        last_month = Period.of(today).previous()
        for period in (last_month.previous(), last_month):
            due_on = await self.rule_book.due_date(period, group)
            if due_on is None or not 0 <= (due_on - today).days <= NOTICE_DAYS:
                continue
            month = await self.declarations(period)
            if month == "tax_module_unavailable":
                return month
            if month == "unknown_year":
                return None
            owed = [card.pending_cents for card in month.cards if card.pending_cents > 0]
            if owed:
                return UpcomingDue(period, due_on, (due_on - today).days, sum(owed), len(owed))
        return None
