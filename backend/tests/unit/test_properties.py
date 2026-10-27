from dataclasses import replace
from datetime import UTC, date, datetime
from uuid import UUID

import pytest

from casero.accounts.application.context import AccountContext
from casero.accounts.domain.profile import Profile, TaxpayerKind
from casero.properties.application.properties import (
    AddUnit,
    CreateProperty,
    UpdateProperty,
    UpdateUnit,
)
from casero.properties.domain.properties import (
    Ownership,
    Property,
    PropertyDetails,
    Unit,
    UnitDetails,
    ownership_fits,
)
from casero.shared.kernel.audit import AuditEntry

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 27, 15, 0, tzinfo=UTC)
CONTEXT = AccountContext(UUID(int=1), UUID(int=2))
HOUSE = PropertyDetails("Casa de Surco", None, None, "sole", None, 100)
ROOM = UnitDetails("Cuarto 1", "room")


@pytest.mark.parametrize(
    ("ownership", "fits_person", "fits_estate"),
    [
        ("sole", True, False),
        ("co_owned", True, False),
        ("conjugal_option", True, False),
        ("conjugal_split", True, False),
        ("estate", False, True),
    ],
)
def test_an_account_declares_either_as_a_person_or_as_an_estate(
    ownership: Ownership, fits_person: bool, fits_estate: bool
) -> None:
    assert ownership_fits(ownership, estate_account=False) == fits_person
    assert ownership_fits(ownership, estate_account=True) == fits_estate


class Clock:
    def now(self) -> datetime:
        return NOW

    def today_lima(self) -> date:
        raise AssertionError("not used")


class Profiles:
    def __init__(self, kind: TaxpayerKind) -> None:
        self.profile = Profile("Ana", kind, None, None, False)

    async def current(self) -> Profile:
        return self.profile

    async def lock_current(self) -> Profile:
        return self.profile

    async def save(self, account_id: UUID, profile: Profile) -> None:
        raise AssertionError("not used")


class Store:
    def __init__(self, *properties: Property) -> None:
        self.properties = {item.id: item for item in properties}
        self.writes: list[str] = []

    async def all(self) -> list[Property]:
        return list(self.properties.values())

    async def lock(self, property_id: UUID) -> Property | None:
        return self.properties.get(property_id)

    async def add(self, account_id: UUID, property_id: UUID, details: PropertyDetails) -> None:
        self.properties[property_id] = Property(property_id, details, False, ())
        self.writes.append("add")

    async def update(self, property_id: UUID, details: PropertyDetails) -> None:
        self.properties[property_id] = replace(self.properties[property_id], details=details)
        self.writes.append("update")

    async def lock_unit(self, unit_id: UUID) -> Unit | None:
        units = (unit for item in self.properties.values() for unit in item.units)
        return next((unit for unit in units if unit.id == unit_id), None)

    async def add_unit(
        self, account_id: UUID, unit_id: UUID, property_id: UUID, details: UnitDetails
    ) -> None:
        self.writes.append("add_unit")

    async def update_unit(self, unit_id: UUID, details: UnitDetails) -> None:
        self.writes.append("update_unit")


class Audit:
    def __init__(self) -> None:
        self.entries: list[AuditEntry] = []

    async def record(self, entry: AuditEntry) -> None:
        self.entries.append(entry)

    def summary(self) -> list[tuple[str, tuple[str, ...]]]:
        return [(entry.action, entry.changed_fields) for entry in self.entries]


def house(archived: bool = False, units: tuple[Unit, ...] = ()) -> Property:
    return Property(UUID(int=10), HOUSE, archived, units)


def room(archived: bool = False) -> Unit:
    return Unit(UUID(int=20), UUID(int=10), ROOM, archived)


async def test_a_property_is_created_with_its_units_and_audited_by_field_name() -> None:
    store, audit = Store(), Audit()
    create = CreateProperty(Profiles("person"), store, audit, Clock())

    result = await create(CONTEXT, HOUSE, [ROOM, UnitDetails("Cochera", "parking")])

    assert isinstance(result, Property)
    assert [unit.details.name for unit in result.units] == ["Cuarto 1", "Cochera"]
    assert store.writes == ["add", "add_unit", "add_unit"]
    property_fields = (
        "name",
        "address_line",
        "district",
        "ownership",
        "autovaluo_cents",
        "rented_share_pct",
    )
    assert audit.summary() == [
        ("property.created", property_fields),
        ("unit.created", ("name", "kind")),
        ("unit.created", ("name", "kind")),
    ]


@pytest.mark.parametrize(
    ("kind", "ownership"), [("person", "estate"), ("estate", "sole"), ("estate", "co_owned")]
)
async def test_the_ownership_must_match_the_declarant(
    kind: TaxpayerKind, ownership: Ownership
) -> None:
    store, audit = Store(), Audit()
    create = CreateProperty(Profiles(kind), store, audit, Clock())

    result = await create(CONTEXT, replace(HOUSE, ownership=ownership), [ROOM])

    assert result == "ownership_mismatch"
    assert (store.writes, audit.entries) == ([], [])


async def test_an_estate_account_registers_estate_properties() -> None:
    create = CreateProperty(Profiles("estate"), Store(), Audit(), Clock())

    result = await create(CONTEXT, replace(HOUSE, ownership="estate"), [ROOM])

    assert isinstance(result, Property)


async def test_editing_a_property_audits_only_what_changed() -> None:
    store, audit = Store(house()), Audit()
    update = UpdateProperty(Profiles("person"), store, audit, Clock())
    details = replace(HOUSE, autovaluo_cents=25_000_000, rented_share_pct=40)

    result = await update(CONTEXT, UUID(int=10), details)

    assert isinstance(result, Property)
    assert result.details == details
    assert audit.summary() == [("property.updated", ("autovaluo_cents", "rented_share_pct"))]


async def test_saving_the_same_property_writes_nothing() -> None:
    store, audit = Store(house()), Audit()
    update = UpdateProperty(Profiles("person"), store, audit, Clock())

    await update(CONTEXT, UUID(int=10), HOUSE)

    assert (store.writes, audit.entries) == ([], [])


@pytest.mark.parametrize(
    ("store", "details", "refusal"),
    [
        (Store(), HOUSE, "not_found"),
        (Store(house(archived=True)), HOUSE, "archived"),
        (Store(house()), replace(HOUSE, ownership="estate"), "ownership_mismatch"),
    ],
)
async def test_some_property_edits_are_refused(
    store: Store, details: PropertyDetails, refusal: str
) -> None:
    update = UpdateProperty(Profiles("person"), store, Audit(), Clock())

    assert await update(CONTEXT, UUID(int=10), details) == refusal
    assert store.writes == []


async def test_units_are_not_added_to_an_archived_property() -> None:
    store = Store(house(archived=True))
    add = AddUnit(store, Audit(), Clock())

    assert await add(CONTEXT, UUID(int=10), ROOM) == "archived"
    assert store.writes == []


async def test_an_archived_unit_is_not_edited() -> None:
    store = Store(house(units=(room(archived=True),)))
    update = UpdateUnit(store, Audit(), Clock())

    assert await update(CONTEXT, UUID(int=20), UnitDetails("Cuarto 2", "room")) == "archived"
    assert store.writes == []
