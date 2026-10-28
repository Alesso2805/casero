import calendar
import re
from dataclasses import dataclass
from datetime import date

PERIOD_PATTERN = re.compile(r"([0-9]{4})-(0[1-9]|1[0-2])")
MONTHS_PER_YEAR = 12


@dataclass(frozen=True, order=True)
class Period:
    """A rent period: one calendar month, written `YYYY-MM` (CLAUDE.md, rule 2)."""

    year: int
    month: int

    @classmethod
    def parse(cls, text: str) -> Period:
        match = PERIOD_PATTERN.fullmatch(text)
        if match is None:
            raise ValueError(f"{text!r} is not a YYYY-MM period")
        return cls(int(match.group(1)), int(match.group(2)))

    @classmethod
    def of(cls, day: date) -> Period:
        return cls(day.year, day.month)

    def __str__(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"

    def first_day(self) -> date:
        return date(self.year, self.month, 1)

    def last_day(self) -> date:
        return date(self.year, self.month, calendar.monthrange(self.year, self.month)[1])

    def next(self) -> Period:
        if self.month == MONTHS_PER_YEAR:
            return Period(self.year + 1, 1)
        return Period(self.year, self.month + 1)


# Rent became taxable when collected from 2026 on; debt from before is only an opening balance
# (SPEC, "Deudas de 2025 o antes"), so no lease is controlled and no receipt is dated earlier.
FIRST_CONTROL_PERIOD = Period(2026, 1)
