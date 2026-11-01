from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class LeaseTools:
    """Whether an active lease keeps WhatsApp and the tenant portal."""

    lease_id: UUID
    created_at: datetime
    enabled: bool


def leases_keeping_tools(leases: Sequence[LeaseTools], limit: int) -> set[UUID]:
    """Within the limit all keep them; over it, the chosen ones and then the oldest (SPEC)."""
    ordered = sorted(
        leases, key=lambda lease: (not lease.enabled, lease.created_at, lease.lease_id)
    )
    return {lease.lease_id for lease in ordered[:limit]}


def tools_changes(
    leases: Sequence[LeaseTools], keep: Collection[UUID]
) -> tuple[list[UUID], list[UUID]]:
    """The leases to turn on and those to turn off, so that only `keep` has them."""
    turn_on = [lease.lease_id for lease in leases if lease.lease_id in keep and not lease.enabled]
    turn_off = [lease.lease_id for lease in leases if lease.lease_id not in keep and lease.enabled]
    return turn_on, turn_off
