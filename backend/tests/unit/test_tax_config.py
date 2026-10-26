import copy
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml

from casero.tax.domain.rules import RUC_GROUPS, TaxRules
from casero.tax.infrastructure.tax_config import (
    TaxConfigError,
    parse,
    read_year,
    seed_dir,
    statements,
    year_files,
)

# R.S. N.° 000281-2022/SUNAT, Anexo I: each group falls due on this business day of the month
# after the period. Used here only to catch typing errors in the YAML files.
BUSINESS_DAY_BY_GROUP = dict(zip(RUC_GROUPS, range(11, 18), strict=True))
SATURDAY = 5


def seed(year: int) -> dict[str, Any]:
    with (seed_dir() / f"{year}.yaml").open(encoding="utf-8") as handle:
        document: dict[str, Any] = yaml.safe_load(handle)
    return document


def nth_business_day(year: int, month: int, nth: int, holidays: set[date]) -> date:
    day = date(year, month, 1)
    count = 0
    while True:
        if day.weekday() < SATURDAY and day not in holidays:
            count += 1
            if count == nth:
                return day
        day += timedelta(days=1)


def test_2026_loads_the_rules_the_spec_names() -> None:
    config = read_year(seed_dir() / "2026.yaml")

    assert config.rules == TaxRules(
        year=2026,
        rate_bp=625,
        deduction_bp=2000,
        rounding="half_up_sol",
        cash_threshold_cents=200000,
        min_rent_bp=600,
        uit_cents=550000,
    )
    assert len(config.due_dates) == 12 * len(RUC_GROUPS)
    assert len(config.holidays) == 16


def test_every_2026_due_date_follows_the_sunat_rule() -> None:
    holidays = set(read_year(seed_dir() / "2026.yaml").holidays) | set(
        read_year(seed_dir() / "2027.yaml").holidays
    )
    config = read_year(seed_dir() / "2026.yaml")

    for (period, group), due in config.due_dates.items():
        year, month = map(int, period.split("-"))
        due_year, due_month = (year + 1, 1) if month == 12 else (year, month + 1)
        expected = nth_business_day(due_year, due_month, BUSINESS_DAY_BY_GROUP[group], holidays)
        assert due == expected, (period, group)


def test_every_seed_file_parses() -> None:
    files = year_files(seed_dir())

    assert [path.stem for path in files] == ["2026", "2027"]
    for path in files:
        assert read_year(path).holidays


def test_statements_upsert_every_row() -> None:
    batches = statements(read_year(seed_dir() / "2026.yaml"))

    assert [len(rows) for _, rows in batches] == [1, 84, 16]


def broken(change: Any) -> dict[str, Any]:
    document = copy.deepcopy(seed(2026))
    change(document)
    return document


@pytest.mark.parametrize(
    ("document", "message"),
    [
        (broken(lambda d: d.update(year=2025)), "year: 2026"),
        (broken(lambda d: d["rules"].pop("source_url")), "source_url"),
        (broken(lambda d: d["holidays"].update(source_url="http://x")), "source_url"),
        (broken(lambda d: d["rules"].update(rate_bp=6.25)), "rate_bp"),
        (broken(lambda d: d["rules"].update(uit_cents=True)), "uit_cents"),
        (broken(lambda d: d["rules"].update(rounding="bankers")), "rounding"),
        (broken(lambda d: d["due_dates"]["periods"].pop("2026-07")), "every period"),
        (broken(lambda d: d["due_dates"]["periods"]["2026-03"].pop("bc")), "groups"),
        (
            broken(lambda d: d["due_dates"]["periods"]["2026-03"].update({"0": date(2026, 3, 31)})),
            "after the period",
        ),
        (broken(lambda d: d["holidays"]["dates"].update({date(2027, 1, 1): "x"})), "of 2026"),
        ({"year": 2026}, "no rules"),
    ],
)
def test_incomplete_or_unsourced_files_are_refused(document: dict[str, Any], message: str) -> None:
    with pytest.raises(TaxConfigError, match=message):
        parse(2026, document)


def test_a_file_must_be_named_after_its_year(tmp_path: Path) -> None:
    path = tmp_path / "rules.yaml"
    path.write_text("year: 2026\n", encoding="utf-8")

    with pytest.raises(TaxConfigError, match="named after its year"):
        read_year(path)
