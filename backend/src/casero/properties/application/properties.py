from collections.abc import Sequence
from dataclasses import dataclass, fields, replace
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from casero.accounts.application.context import AccountContext
from casero.accounts.application.profile import Profiles
from casero.properties.domain.properties import (
    Property,
    PropertyDetails,
    Unit,
    UnitDetails,
    ownership_fits,
)
from casero.shared.kernel.audit import AuditEntry, AuditLog
from casero.shared.kernel.clock import Clock
from casero.shared.kernel.ids import new_id


class PropertyStore(Protocol):
    async def all(self) -> list[Property]: ...

    async def lock(self, property_id: UUID) -> Property | None:
        """Locks the property and its units, in that order."""
        ...

    async def add(self, account_id: UUID, property_id: UUID, details: PropertyDetails) -> None: ...

    async def update(self, property_id: UUID, details: PropertyDetails) -> None: ...

    async def archive(self, property_id: UUID, at: datetime) -> None:
        """Archives the property and its units that are still in use."""
        ...

    async def lock_unit(self, unit_id: UUID) -> Unit | None: ...

    async def add_unit(
        self, account_id: UUID, unit_id: UUID, property_id: UUID, details: UnitDetails
    ) -> None: ...

    async def update_unit(self, unit_id: UUID, details: UnitDetails) -> None: ...

    async def archive_unit(self, unit_id: UUID, at: datetime) -> None: ...


class ActiveLeases(Protocol):
    """Implemented by leases (AR-03); callers hold the unit locks so no lease starts meanwhile."""

    async def on_unit(self, unit_id: UUID) -> bool: ...

    async def on_property(self, property_id: UUID) -> bool: ...


def audit_entry(
    context: AccountContext,
    action: str,
    entity: str,
    entity_id: UUID,
    changed_fields: Sequence[str],
    at: datetime,
) -> AuditEntry:
    return AuditEntry.of(
        context.account_id, context.user_id, action, entity, entity_id, changed_fields, at
    )


def field_names(details: PropertyDetails | UnitDetails) -> list[str]:
    return [field.name for field in fields(details)]


@dataclass(frozen=True)
class ListProperties:
    store: PropertyStore

    async def __call__(self) -> list[Property]:
        return await self.store.all()


@dataclass(frozen=True)
class CreateProperty:
    profiles: Profiles
    store: PropertyStore
    audit: AuditLog
    clock: Clock

    async def __call__(
        self, context: AccountContext, details: PropertyDetails, units: Sequence[UnitDetails]
    ) -> Property | Literal["ownership_mismatch"]:
        declarant = await self.profiles.lock_current()
        if not ownership_fits(details.ownership, declarant.taxpayer_kind == "estate"):
            return "ownership_mismatch"
        now = self.clock.now()
        property_id = new_id()
        await self.store.add(context.account_id, property_id, details)
        await self.audit.record(
            audit_entry(
                context, "property.created", "properties", property_id, field_names(details), now
            )
        )
        created: list[Unit] = []
        for unit_details in units:
            unit = Unit(new_id(), property_id, unit_details, archived=False)
            await self.store.add_unit(context.account_id, unit.id, property_id, unit_details)
            await self.audit.record(
                audit_entry(
                    context, "unit.created", "units", unit.id, field_names(unit_details), now
                )
            )
            created.append(unit)
        return Property(property_id, details, archived=False, units=tuple(created))


@dataclass(frozen=True)
class UpdateProperty:
    profiles: Profiles
    store: PropertyStore
    audit: AuditLog
    clock: Clock

    async def __call__(
        self, context: AccountContext, property_id: UUID, details: PropertyDetails
    ) -> Property | Literal["not_found", "archived", "ownership_mismatch"]:
        declarant = await self.profiles.lock_current()
        current = await self.store.lock(property_id)
        if current is None:
            return "not_found"
        if current.archived:
            return "archived"
        if not ownership_fits(details.ownership, declarant.taxpayer_kind == "estate"):
            return "ownership_mismatch"
        changed = current.details.changed_fields(details)
        if changed:
            await self.store.update(property_id, details)
            await self.audit.record(
                audit_entry(
                    context,
                    "property.updated",
                    "properties",
                    property_id,
                    changed,
                    self.clock.now(),
                )
            )
        return replace(current, details=details)


@dataclass(frozen=True)
class ArchiveProperty:
    store: PropertyStore
    leases: ActiveLeases
    audit: AuditLog
    clock: Clock

    async def __call__(
        self, context: AccountContext, property_id: UUID
    ) -> Property | Literal["not_found", "active_lease"]:
        current = await self.store.lock(property_id)
        if current is None:
            return "not_found"
        if current.archived:
            return current
        if await self.leases.on_property(property_id):
            return "active_lease"
        now = self.clock.now()
        await self.store.archive(property_id, now)
        await self.audit.record(
            audit_entry(
                context, "property.archived", "properties", property_id, ["archived_at"], now
            )
        )
        units = tuple(replace(unit, archived=True) for unit in current.units)
        return replace(current, archived=True, units=units)


@dataclass(frozen=True)
class AddUnit:
    store: PropertyStore
    audit: AuditLog
    clock: Clock

    async def __call__(
        self, context: AccountContext, property_id: UUID, details: UnitDetails
    ) -> Unit | Literal["not_found", "archived"]:
        current = await self.store.lock(property_id)
        if current is None:
            return "not_found"
        if current.archived:
            return "archived"
        unit = Unit(new_id(), property_id, details, archived=False)
        await self.store.add_unit(context.account_id, unit.id, property_id, details)
        await self.audit.record(
            audit_entry(
                context, "unit.created", "units", unit.id, field_names(details), self.clock.now()
            )
        )
        return unit


@dataclass(frozen=True)
class UpdateUnit:
    store: PropertyStore
    audit: AuditLog
    clock: Clock

    async def __call__(
        self, context: AccountContext, unit_id: UUID, details: UnitDetails
    ) -> Unit | Literal["not_found", "archived"]:
        current = await self.store.lock_unit(unit_id)
        if current is None:
            return "not_found"
        if current.archived:
            return "archived"
        changed = current.details.changed_fields(details)
        if changed:
            await self.store.update_unit(unit_id, details)
            await self.audit.record(
                audit_entry(context, "unit.updated", "units", unit_id, changed, self.clock.now())
            )
        return replace(current, details=details)


@dataclass(frozen=True)
class ArchiveUnit:
    store: PropertyStore
    leases: ActiveLeases
    audit: AuditLog
    clock: Clock

    async def __call__(
        self, context: AccountContext, unit_id: UUID
    ) -> Unit | Literal["not_found", "active_lease"]:
        current = await self.store.lock_unit(unit_id)
        if current is None:
            return "not_found"
        if current.archived:
            return current
        if await self.leases.on_unit(unit_id):
            return "active_lease"
        now = self.clock.now()
        await self.store.archive_unit(unit_id, now)
        await self.audit.record(
            audit_entry(context, "unit.archived", "units", unit_id, ["archived_at"], now)
        )
        return replace(current, archived=True)
