from datetime import date
from pathlib import Path

import asyncpg
import pytest

from casero.tax.infrastructure.tax_config import load_all, seed_dir
from database import Database

pytestmark = pytest.mark.anyio

COUNTS = """
SELECT (SELECT count(*) FROM tax_rule_sets WHERE year = $1),
       (SELECT count(*) FROM sunat_due_dates WHERE year = $1),
       (SELECT count(*) FROM holidays WHERE extract(year FROM date) = $1)
"""


async def counts(database: Database, year: int) -> tuple[int, int, int]:
    owner = await asyncpg.connect(database.dsn("casero_owner"))
    try:
        row = await owner.fetchrow(COUNTS, year)
        assert row is not None
        return (row[0], row[1], row[2])
    finally:
        await owner.close()


def owner_url(database: Database) -> str:
    return database.dsn("casero_owner").replace("postgresql://", "postgresql+asyncpg://", 1)


async def test_the_migration_loads_2026(database: Database) -> None:
    assert await counts(database, 2026) == (1, 84, 16)

    app = await asyncpg.connect(database.dsn("casero_app"))
    try:
        rule = await app.fetchrow("SELECT rate_bp, uit_cents FROM tax_rule_sets WHERE year = 2026")
        due = await app.fetchval(
            "SELECT due_date FROM sunat_due_dates WHERE period = '2026-12' AND ruc_group = 'bc'"
        )
    finally:
        await app.close()
    assert rule is not None
    assert tuple(rule) == (625, 550000)
    assert due == date(2027, 1, 26)


async def test_loading_every_year_is_idempotent(database: Database) -> None:
    years = await load_all(owner_url(database), seed_dir())
    again = await load_all(owner_url(database), seed_dir())

    assert years == again == [2026, 2027]
    assert await counts(database, 2026) == (1, 84, 16)
    assert await counts(database, 2027) == (0, 0, 16)


async def test_a_corrected_file_updates_the_loaded_values(
    database: Database, tmp_path: Path
) -> None:
    (tmp_path / "2031.yaml").write_text(
        "year: 2031\n"
        "holidays:\n"
        "  source_url: https://busquedas.elperuano.pe/dispositivo/NL/2194316-1\n"
        "  dates:\n"
        "    2031-01-01: Año\n",
        encoding="utf-8",
    )
    await load_all(owner_url(database), tmp_path)
    (tmp_path / "2031.yaml").write_text(
        (tmp_path / "2031.yaml").read_text(encoding="utf-8").replace("Año", "Año Nuevo"),
        encoding="utf-8",
    )

    await load_all(owner_url(database), tmp_path)

    owner = await asyncpg.connect(database.dsn("casero_owner"))
    try:
        assert await owner.fetchval("SELECT name FROM holidays WHERE date = '2031-01-01'") == (
            "Año Nuevo"
        )
    finally:
        await owner.close()
