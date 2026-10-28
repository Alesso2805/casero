"""Load the yearly tax configuration from infra/seed/tax/{year}.yaml (CLAUDE.md, rule 6).

Run as casero_owner: `python -m casero.tax.infrastructure.tax_config` upserts every year file.
The migrator runs it on each start, and `make load-tax-config` runs it locally.
"""

import asyncio
import calendar
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import TextClause, text

from casero.shared.infrastructure.database import create_engine
from casero.tax.domain.rules import ROUNDING_METHODS, RUC_GROUPS, RucGroup, TaxRules

MONTHS = range(1, 13)
RULE_FIELDS = (
    "rate_bp",
    "deduction_bp",
    "cash_threshold_cents",
    "min_rent_bp",
    "uit_cents",
)

UPSERT_RULES = text(
    "INSERT INTO tax_rule_sets (year, rate_bp, deduction_bp, rounding, cash_threshold_cents,"
    " min_rent_bp, uit_cents, source_url)"
    " VALUES (:year, :rate_bp, :deduction_bp, :rounding, :cash_threshold_cents, :min_rent_bp,"
    " :uit_cents, :source_url)"
    " ON CONFLICT (year) DO UPDATE SET rate_bp = EXCLUDED.rate_bp,"
    " deduction_bp = EXCLUDED.deduction_bp, rounding = EXCLUDED.rounding,"
    " cash_threshold_cents = EXCLUDED.cash_threshold_cents, min_rent_bp = EXCLUDED.min_rent_bp,"
    " uit_cents = EXCLUDED.uit_cents, source_url = EXCLUDED.source_url"
)
UPSERT_DUE_DATE = text(
    "INSERT INTO sunat_due_dates (year, period, ruc_group, due_date, source_url)"
    " VALUES (:year, :period, :ruc_group, :due_date, :source_url)"
    " ON CONFLICT (year, period, ruc_group) DO UPDATE SET due_date = EXCLUDED.due_date,"
    " source_url = EXCLUDED.source_url"
)
UPSERT_HOLIDAY = text(
    "INSERT INTO holidays (date, name) VALUES (:date, :name)"
    " ON CONFLICT (date) DO UPDATE SET name = EXCLUDED.name"
)


class TaxConfigError(ValueError):
    pass


@dataclass(frozen=True)
class TaxYearConfig:
    year: int
    rules: TaxRules | None
    rules_source: str | None
    due_dates: dict[tuple[str, RucGroup], date]
    due_dates_source: str | None
    holidays: dict[date, str]


def seed_dir() -> Path:
    configured = os.environ.get("CASERO_TAX_SEED_DIR")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[5] / "infra" / "seed" / "tax"


def _section(document: dict[str, Any], name: str) -> tuple[dict[str, Any], str] | None:
    section = document.get(name)
    if section is None:
        return None
    if not isinstance(section, dict):
        raise TaxConfigError(f"{name} must be a mapping")
    source = section.get("source_url")
    if not isinstance(source, str) or not source.startswith("https://"):
        raise TaxConfigError(f"{name} needs an https source_url")
    return section, source


def _rules(year: int, section: dict[str, Any]) -> TaxRules:
    values = {}
    for field in RULE_FIELDS:
        value = section.get(field)
        if type(value) is not int or value < 0:
            raise TaxConfigError(f"rules.{field} must be a non-negative integer")
        values[field] = value
    rounding = section.get("rounding")
    if rounding not in ROUNDING_METHODS:
        raise TaxConfigError(f"rules.rounding must be one of {ROUNDING_METHODS}")
    return TaxRules(year=year, rounding=rounding, **values)


def _due_dates(year: int, section: dict[str, Any]) -> dict[tuple[str, RucGroup], date]:
    periods = section.get("periods")
    expected = [f"{year}-{month:02d}" for month in MONTHS]
    if not isinstance(periods, dict) or sorted(periods) != expected:
        raise TaxConfigError(f"due_dates.periods must list every period of {year}")
    due_dates: dict[tuple[str, RucGroup], date] = {}
    for month, period in zip(MONTHS, expected, strict=True):
        groups = periods[period]
        if not isinstance(groups, dict) or set(groups) != set(RUC_GROUPS):
            raise TaxConfigError(f"{period} must have the groups {RUC_GROUPS}")
        period_end = date(year, month, calendar.monthrange(year, month)[1])
        for group in RUC_GROUPS:
            due = groups[group]
            if not isinstance(due, date) or due <= period_end:
                raise TaxConfigError(f"{period} group {group} must fall due after the period")
            due_dates[period, group] = due
    return due_dates


def _holidays(year: int, section: dict[str, Any]) -> dict[date, str]:
    dates = section.get("dates")
    if not isinstance(dates, dict) or not dates:
        raise TaxConfigError("holidays.dates must list the holidays")
    for day, name in dates.items():
        if not isinstance(day, date) or day.year != year:
            raise TaxConfigError(f"holiday {day} is not a date of {year}")
        if not isinstance(name, str) or not name.strip():
            raise TaxConfigError(f"holiday {day} needs a name")
    return dict(dates)


def parse(expected_year: int, document: Any) -> TaxYearConfig:
    if not isinstance(document, dict) or document.get("year") != expected_year:
        raise TaxConfigError(f"the file must say year: {expected_year}")
    rules = _section(document, "rules")
    due_dates = _section(document, "due_dates")
    holidays = _section(document, "holidays")
    if rules is None and due_dates is None and holidays is None:
        raise TaxConfigError("the file has no rules, due_dates or holidays")
    return TaxYearConfig(
        year=expected_year,
        rules=_rules(expected_year, rules[0]) if rules else None,
        rules_source=rules[1] if rules else None,
        due_dates=_due_dates(expected_year, due_dates[0]) if due_dates else {},
        due_dates_source=due_dates[1] if due_dates else None,
        holidays=_holidays(expected_year, holidays[0]) if holidays else {},
    )


def read_year(path: Path) -> TaxYearConfig:
    try:
        year = int(path.stem)
    except ValueError as error:
        raise TaxConfigError(f"{path.name} must be named after its year") from error
    with path.open(encoding="utf-8") as handle:
        return parse(year, yaml.safe_load(handle))


def statements(config: TaxYearConfig) -> list[tuple[TextClause, list[dict[str, Any]]]]:
    batches: list[tuple[TextClause, list[dict[str, Any]]]] = []
    if config.rules:
        rules = config.rules
        batches.append(
            (
                UPSERT_RULES,
                [
                    {
                        "year": rules.year,
                        "rate_bp": rules.rate_bp,
                        "deduction_bp": rules.deduction_bp,
                        "rounding": rules.rounding,
                        "cash_threshold_cents": rules.cash_threshold_cents,
                        "min_rent_bp": rules.min_rent_bp,
                        "uit_cents": rules.uit_cents,
                        "source_url": config.rules_source,
                    }
                ],
            )
        )
    if config.due_dates:
        batches.append(
            (
                UPSERT_DUE_DATE,
                [
                    {
                        "year": config.year,
                        "period": period,
                        "ruc_group": group,
                        "due_date": due,
                        "source_url": config.due_dates_source,
                    }
                    for (period, group), due in sorted(config.due_dates.items())
                ],
            )
        )
    if config.holidays:
        batches.append(
            (
                UPSERT_HOLIDAY,
                [{"date": day, "name": name} for day, name in sorted(config.holidays.items())],
            )
        )
    return batches


def year_files(directory: Path) -> list[Path]:
    return sorted(directory.glob("[0-9][0-9][0-9][0-9].yaml"))


async def load_all(database_url: str, directory: Path) -> list[int]:
    configs = [read_year(path) for path in year_files(directory)]
    engine = create_engine(database_url)
    try:
        async with engine.begin() as connection:
            for config in configs:
                for statement, rows in statements(config):
                    await connection.execute(statement, rows)
    finally:
        await engine.dispose()
    return [config.year for config in configs]


def main() -> None:
    years = asyncio.run(load_all(os.environ["CASERO_MIGRATION_DATABASE_URL"], seed_dir()))
    print(f"Tax configuration loaded: {', '.join(map(str, years))}")


if __name__ == "__main__":
    main()
