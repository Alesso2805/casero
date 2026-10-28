from dataclasses import dataclass
from datetime import date
from typing import Protocol
from uuid import UUID

from casero.shared.kernel.audit import AuditEntry, AuditLog
from casero.shared.kernel.clock import Clock


class LeaseClosings(Protocol):
    async def overdue(self, today: date) -> list[tuple[UUID, date]]:
        """Active leases whose planned end is before today, with that end."""
        ...

    async def close(self, lease_id: UUID, ended_at: date) -> None: ...


@dataclass(frozen=True)
class CloseExpiredLeases:
    """A lease not renewed by its planned end closes on that date (SPEC, "Activo")."""

    closings: LeaseClosings
    audit: AuditLog
    clock: Clock

    async def __call__(self, account_id: UUID, today: date) -> int:
        overdue = await self.closings.overdue(today)
        for lease_id, end_date in overdue:
            await self.closings.close(lease_id, end_date)
            await self.audit.record(
                AuditEntry.of(
                    account_id,
                    None,
                    "lease.closed",
                    "leases",
                    lease_id,
                    ["ended_at"],
                    self.clock.now(),
                )
            )
        return len(overdue)
