from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from casero.identity.application.unsubscribe import UserEmails
from casero.identity.domain.email_suppressions import ScheduledEmailKind, Suppression
from casero.shared.kernel.clock import Clock


class Unsubscriptions(Protocol):
    async def unsubscribed(self, email: str, kind: ScheduledEmailKind) -> bool: ...

    async def add(self, suppression: Suppression, now: datetime) -> None: ...

    async def resubscribe(self, email: str, kind: ScheduledEmailKind) -> None:
        """Removes only this address's unsubscribe from that kind; bounces and complaints stay."""
        ...


@dataclass(frozen=True)
class EmailChoices:
    """Which scheduled emails a user gets: an unsubscribe, from a link or from Mis datos."""

    users: UserEmails
    store: Unsubscriptions
    clock: Clock

    async def wants(self, user_id: UUID, kind: ScheduledEmailKind) -> bool:
        email = await self.users.email_of(user_id)
        return email is not None and not await self.store.unsubscribed(email, kind)

    async def choose(self, user_id: UUID, kind: ScheduledEmailKind, wanted: bool) -> None:
        email = await self.users.email_of(user_id)
        if email is None:
            return
        if wanted:
            await self.store.resubscribe(email, kind)
        else:
            await self.store.add(Suppression(email, kind, "unsubscribe"), self.clock.now())
