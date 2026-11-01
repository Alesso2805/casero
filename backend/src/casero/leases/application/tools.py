from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from casero.accounts.application.context import AccountContext
from casero.accounts.application.entitlements import GetEntitlements
from casero.accounts.application.profile import Profiles
from casero.leases.domain.tools import LeaseTools, leases_keeping_tools, tools_changes
from casero.shared.kernel.audit import AuditEntry, AuditLog
from casero.shared.kernel.clock import Clock


class LeaseToolsStore(Protocol):
    async def active(self) -> list[LeaseTools]: ...

    async def set_enabled(self, lease_ids: Sequence[UUID], enabled: bool) -> None: ...


@dataclass(frozen=True)
class ToolsStatus:
    limit: int
    leases: list[LeaseTools]

    @property
    def over_limit(self) -> bool:
        return len(self.leases) > self.limit


async def apply_tools(
    store: LeaseToolsStore,
    audit: AuditLog,
    account_id: UUID,
    actor: UUID | None,
    leases: Sequence[LeaseTools],
    keep: set[UUID],
    at: datetime,
) -> list[LeaseTools]:
    turn_on, turn_off = tools_changes(leases, keep)
    for lease_ids, enabled in ((turn_on, True), (turn_off, False)):
        if lease_ids:
            await store.set_enabled(lease_ids, enabled)
    for lease_id in (*turn_on, *turn_off):
        await audit.record(
            AuditEntry.of(
                account_id, actor, "lease.tools_changed", "leases", lease_id, ["tools_enabled"], at
            )
        )
    return [replace(lease, enabled=lease.lease_id in keep) for lease in leases]


@dataclass(frozen=True)
class GetLeaseTools:
    entitlements: GetEntitlements
    store: LeaseToolsStore

    async def __call__(self) -> ToolsStatus:
        entitlements = await self.entitlements()
        return ToolsStatus(entitlements.plan.max_active_leases, await self.store.active())


@dataclass(frozen=True)
class ChooseLeaseTools:
    """The landlord picks who keeps the tools; the rest of the limit goes to the oldest."""

    entitlements: GetEntitlements
    profiles: Profiles
    store: LeaseToolsStore
    audit: AuditLog
    clock: Clock

    async def __call__(
        self, context: AccountContext, chosen: Sequence[UUID]
    ) -> ToolsStatus | Literal["lease_not_found", "too_many_leases"]:
        await self.profiles.lock_current()
        limit = (await self.entitlements()).plan.max_active_leases
        leases = await self.store.active()
        if set(chosen) - {lease.lease_id for lease in leases}:
            return "lease_not_found"
        if len(set(chosen)) > limit:
            return "too_many_leases"
        marked = [replace(lease, enabled=lease.lease_id in chosen) for lease in leases]
        keep = leases_keeping_tools(marked, limit)
        updated = await apply_tools(
            self.store,
            self.audit,
            context.account_id,
            context.user_id,
            leases,
            keep,
            self.clock.now(),
        )
        return ToolsStatus(limit, updated)


@dataclass(frozen=True)
class EnsureLeaseTools:
    """Keeps the flag in step with the plan: a lapsed plan cuts it back, a paid one restores it."""

    entitlements: GetEntitlements
    store: LeaseToolsStore
    audit: AuditLog
    clock: Clock

    async def __call__(self, account_id: UUID) -> None:
        limit = (await self.entitlements()).plan.max_active_leases
        leases = await self.store.active()
        keep = leases_keeping_tools(leases, limit)
        await apply_tools(self.store, self.audit, account_id, None, leases, keep, self.clock.now())
