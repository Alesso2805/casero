import io
import json
import zipfile
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from casero.accounts.application.data_export import data_archive
from casero.shared.kernel.data_sections import DataSection, plain_cell

AT = datetime(2026, 11, 1, 15, 0, tzinfo=UTC)


def test_dates_and_ids_become_text_and_the_rest_stays_as_it_is() -> None:
    assert [
        plain_cell(value)
        for value in (UUID(int=1), AT, date(2026, 11, 1), "Ana", 80_000, True, None)
    ] == [
        str(UUID(int=1)),
        "2026-11-01T15:00:00+00:00",
        "2026-11-01",
        "Ana",
        80_000,
        True,
        None,
    ]


def test_a_type_without_a_format_fails_instead_of_exporting_something_odd() -> None:
    with pytest.raises(TypeError):
        plain_cell(Decimal("1.5"))


def test_the_archive_has_a_json_with_everything_and_one_csv_per_section() -> None:
    sections = [
        DataSection("pagos", ("id", "nota"), [("1", "=SUMA(A1)"), ("2", None)]),
        DataSection("garantias", ("id",), []),
    ]

    archive = zipfile.ZipFile(io.BytesIO(data_archive(sections, AT)))

    assert archive.namelist() == ["datos.json", "pagos.csv", "garantias.csv"]
    assert json.loads(archive.read("datos.json")) == {
        "exportado_el": "2026-11-01T15:00:00+00:00",
        "secciones": {
            "pagos": [{"id": "1", "nota": "=SUMA(A1)"}, {"id": "2", "nota": None}],
            "garantias": [],
        },
    }
    assert archive.read("pagos.csv").decode("utf-8-sig") == ("id,nota\r\n1,'=SUMA(A1)\r\n2,\r\n")
    assert archive.read("garantias.csv").decode("utf-8-sig") == "id\r\n"
    assert archive.getinfo("pagos.csv").date_time == (2026, 11, 1, 15, 0, 0)
