from casero.tax.application.exports import csv_text, soles, spreadsheet_cell


def test_cells_a_spreadsheet_would_run_as_formulas_are_quoted() -> None:
    assert [spreadsheet_cell(v) for v in ("=SUM(A1)", "+1", "-5", "@x", "\tx", "Ana", "")] == [
        "'=SUM(A1)",
        "'+1",
        "'-5",
        "'@x",
        "'\tx",
        "Ana",
        "",
    ]


def test_the_file_opens_in_excel_with_accents_and_quotes_commas() -> None:
    text = csv_text(("Período", "Nota"), [("2026-10", "Luz, agua")])

    assert text == '﻿Período,Nota\r\n2026-10,"Luz, agua"\r\n'


def test_amounts_are_soles_with_two_decimals() -> None:
    assert [soles(c) for c in (55_100, 5, 0)] == ["551.00", "0.05", "0.00"]
