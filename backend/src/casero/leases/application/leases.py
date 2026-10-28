from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol
from uuid import UUID

from casero.leases.domain.leases import (
    Lease,
    LeaseProblem,
    LeaseTerms,
    OpeningBalances,
    TaxTreatment,
    effective_treatment,
    lease_problem,
    opening_balance_due,
)
from casero.shared.kernel.clock import Clock
from casero.shared.kernel.periods import Period

__all__ = [
    "Lease",
    "LeaseProblem",
    "LeaseStore",
    "LeaseTerms",
    "LeaseView",
    "ListLeases",
    "OpeningBalances",
    "TaxTreatment",
    "effective_treatment",
    "lease_problem",
    "opening_balance_due",
    "view",
]


class LeaseStore(Protocol):
    async def get(self, lease_id: UUID, period: Period) -> Lease | None: ...

    async def all(self, period: Period) -> list[Lease]: ...

    async def count_active(self) -> int: ...

    async def active_on_unit(self, unit_id: UUID) -> bool: ...

    async def add(
        self, account_id: UUID, lease_id: UUID, terms: LeaseTerms, created_at: datetime
    ) -> bool:
        """False when the id already exists, in this account or another (rule 5)."""
        ...

    async def add_rent_change(
        self,
        account_id: UUID,
        change_id: UUID,
        lease_id: UUID,
        monthly_rent_cents: int,
        effective_period: Period,
        created_by: UUID,
        created_at: datetime,
    ) -> None: ...


@dataclass(frozen=True)
class LeaseView:
    lease: Lease
    days_to_end: int | None
    ending_soon: bool


def view(lease: Lease, today: date) -> LeaseView:
    return LeaseView(lease, lease.days_to_end(today), lease.ending_soon(today))


@dataclass(frozen=True)
class ListLeases:
    store: LeaseStore
    clock: Clock

    async def __call__(self) -> list[LeaseView]:
        today = self.clock.today_lima()
        return [view(lease, today) for lease in await self.store.all(Period.of(today))]
