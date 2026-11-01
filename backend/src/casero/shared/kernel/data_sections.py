from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

type Cell = str | int | bool | None


@dataclass(frozen=True)
class DataSection:
    """One table of the legal data export, with plain values ready for JSON and CSV."""

    name: str
    columns: tuple[str, ...]
    rows: list[tuple[Cell, ...]]


def plain_cell(value: object) -> Cell:
    match value:
        case None | bool() | int() | str():
            return value
        case UUID():
            return str(value)
        case datetime() | date():
            return value.isoformat()
    raise TypeError(f"The data export has no format for {type(value).__name__}")
