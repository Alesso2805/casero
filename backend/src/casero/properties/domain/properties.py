from dataclasses import dataclass, fields
from typing import Literal
from uuid import UUID

Ownership = Literal["sole", "co_owned", "conjugal_option", "conjugal_split", "estate"]
UnitKind = Literal["room", "mini_apartment", "apartment", "shop", "parking", "other"]


def changes_split(before: Ownership, after: Ownership) -> bool:
    """Leases take their tax treatment from conjugal_split when they start; it can't flip."""
    return (before == "conjugal_split") != (after == "conjugal_split")


def ownership_fits(ownership: Ownership, estate_account: bool) -> bool:
    """An account is one declarant: an estate declares only its own properties, and only it."""
    return (ownership == "estate") == estate_account


@dataclass(frozen=True)
class PropertyDetails:
    name: str
    address_line: str | None
    district: str | None
    ownership: Ownership
    autovaluo_cents: int | None
    rented_share_pct: int

    def changed_fields(self, other: PropertyDetails) -> list[str]:
        return [
            field.name
            for field in fields(self)
            if getattr(self, field.name) != getattr(other, field.name)
        ]


@dataclass(frozen=True)
class UnitDetails:
    name: str
    kind: UnitKind

    def changed_fields(self, other: UnitDetails) -> list[str]:
        return [
            field.name
            for field in fields(self)
            if getattr(self, field.name) != getattr(other, field.name)
        ]


@dataclass(frozen=True)
class Unit:
    id: UUID
    property_id: UUID
    details: UnitDetails
    archived: bool


@dataclass(frozen=True)
class Property:
    id: UUID
    details: PropertyDetails
    archived: bool
    units: tuple[Unit, ...]
