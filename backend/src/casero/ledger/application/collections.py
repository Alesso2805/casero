from dataclasses import dataclass
from datetime import date
from typing import Protocol
from uuid import UUID

from casero.ledger.domain.allocation import Charge, Payment
from casero.ledger.domain.collections import URGENCY, LeaseCollection, collection
from casero.shared.kernel.clock import Clock


@dataclass(frozen=True)
class LeaseBook:
    lease_id: UUID
    ended: bool
    charges: list[Charge]
    payments: list[Payment]


class CollectionsStore(Protocol):
    async def lease_books(self) -> list[LeaseBook]:
        """Every lease of the account in context, with its charges and payments."""
        ...


@dataclass(frozen=True)
class CollectionLine:
    lease_id: UUID
    ended: bool
    collection: LeaseCollection


@dataclass(frozen=True)
class Collections:
    leases: list[CollectionLine]
    due_by_month_end_cents: int
    overdue_cents: int


def urgency(line: CollectionLine) -> tuple[int, int, int, date, UUID]:
    standing = line.collection
    return (
        URGENCY.index(standing.status),
        -standing.overdue_days,
        -standing.overdue_cents,
        standing.next_due_on or date.max,
        line.lease_id,
    )


@dataclass(frozen=True)
class GetCollections:
    """Active leases, and ended ones that still owe, most urgent first (SPEC, "Panel")."""

    store: CollectionsStore
    clock: Clock

    async def __call__(self) -> Collections:
        today = self.clock.today_lima()
        lines = []
        for book in await self.store.lease_books():
            standing = collection(book.charges, book.payments, today)
            if not book.ended or standing.balance_cents > 0:
                lines.append(CollectionLine(book.lease_id, book.ended, standing))
        lines.sort(key=urgency)
        return Collections(
            lines,
            sum(line.collection.due_by_month_end_cents for line in lines),
            sum(line.collection.overdue_cents for line in lines),
        )
