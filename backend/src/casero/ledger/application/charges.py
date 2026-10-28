from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol
from uuid import UUID

from casero.ledger.domain.charges import LeaseToCharge, RentCharge, missing_rent_charges
from casero.shared.kernel.clock import Clock
from casero.shared.kernel.ids import new_id


class RentChargeStore(Protocol):
    async def leases_to_charge(self, lease_id: UUID | None) -> list[LeaseToCharge]: ...

    async def add_rent(
        self, account_id: UUID, charge_id: UUID, charge: RentCharge, created_at: datetime
    ) -> None:
        """Does nothing if the period already has a rent charge (one per lease and period)."""
        ...


@dataclass(frozen=True)
class EnsureRentCharges:
    """Brings the account's rent charges up to today; running it again creates nothing."""

    store: RentChargeStore
    clock: Clock

    async def __call__(self, account_id: UUID, today: date, lease_id: UUID | None = None) -> int:
        created = 0
        for lease in await self.store.leases_to_charge(lease_id):
            for charge in missing_rent_charges(lease, today):
                await self.store.add_rent(account_id, new_id(), charge, self.clock.now())
                created += 1
        return created
