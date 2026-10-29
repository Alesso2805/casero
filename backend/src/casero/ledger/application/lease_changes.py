from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

from casero.accounts.application.context import AccountContext
from casero.leases.application.leases import LeaseStore, RentChangeRecord
from casero.shared.kernel.audit import AuditEntry, AuditLog
from casero.shared.kernel.clock import Clock
from casero.shared.kernel.periods import Period


class ChargedPeriods(Protocol):
    async def lock_lease(self, lease_id: UUID) -> bool: ...

    async def last_rent_period(self, lease_id: UUID) -> Period | None:
        """The latest period with a rent or correction, voided ones included."""
        ...


@dataclass(frozen=True)
class NewRent:
    id: UUID
    lease_id: UUID
    monthly_rent_cents: int


@dataclass(frozen=True)
class RentChanged:
    change: RentChangeRecord
    replayed: bool


@dataclass(frozen=True)
class ChangeRent:
    """A new rent from the next period not yet charged; charged ones keep theirs (SPEC)."""

    leases: LeaseStore
    periods: ChargedPeriods
    audit: AuditLog
    clock: Clock

    async def __call__(
        self, context: AccountContext, new: NewRent
    ) -> RentChanged | Literal["lease_not_found", "lease_ended", "conflict"]:
        if not await self.periods.lock_lease(new.lease_id):
            return "lease_not_found"
        existing = await self.leases.rent_change(new.id)
        if existing is not None:
            matches = (existing.lease_id, existing.monthly_rent_cents) == (
                new.lease_id,
                new.monthly_rent_cents,
            )
            return RentChanged(existing, True) if matches else "conflict"
        lease = await self.leases.get(new.lease_id, Period.of(self.clock.today_lima()))
        if lease is None:
            return "lease_not_found"
        if lease.ended_at is not None:
            return "lease_ended"
        last = await self.periods.last_rent_period(new.lease_id)
        effective = last.next() if last else lease.terms.control_from
        now = self.clock.now()
        added = await self.leases.add_rent_change(
            context.account_id,
            new.id,
            new.lease_id,
            new.monthly_rent_cents,
            effective,
            context.user_id,
            now,
        )
        if not added:
            return "conflict"
        await self.audit.record(
            AuditEntry.of(
                context.account_id,
                context.user_id,
                "lease.rent_changed",
                "lease_rent_changes",
                new.id,
                ["monthly_rent_cents", "effective_period"],
                now,
            )
        )
        return RentChanged(
            RentChangeRecord(new.id, new.lease_id, new.monthly_rent_cents, effective), False
        )
