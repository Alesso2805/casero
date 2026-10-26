from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from casero.identity.application.email_suppressions import SuppressionStore
from casero.identity.domain.email_suppressions import ScheduledEmailKind, Suppression
from casero.shared.kernel.clock import Clock


class UnsubscribeTokens(Protocol):
    def valid(self, user_id: UUID, kind: ScheduledEmailKind, token: str) -> bool: ...


class UserEmails(Protocol):
    async def email_of(self, user_id: UUID) -> str | None: ...


@dataclass(frozen=True)
class Unsubscribe:
    tokens: UnsubscribeTokens
    users: UserEmails
    store: SuppressionStore
    clock: Clock

    async def __call__(self, user_id: UUID, kind: ScheduledEmailKind, token: str) -> bool:
        if not self.tokens.valid(user_id, kind, token):
            return False
        email = await self.users.email_of(user_id)
        if email is not None:
            await self.store.add(Suppression(email, kind, "unsubscribe"), self.clock.now())
        return True
