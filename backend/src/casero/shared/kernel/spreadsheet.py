import csv
import io
from collections.abc import Iterable, Sequence

# A spreadsheet runs a cell that starts with one of these as a formula (CSV injection).
FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")
# Excel needs the BOM to read the file as UTF-8, or the accents break.
UTF8_BOM = "﻿"


def spreadsheet_cell(value: str) -> str:
    return f"'{value}" if value.startswith(FORMULA_STARTS) else value


def csv_text(columns: Sequence[str], rows: Iterable[Sequence[str]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(columns)
    writer.writerows([spreadsheet_cell(value) for value in row] for row in rows)
    return UTF8_BOM + buffer.getvalue()
