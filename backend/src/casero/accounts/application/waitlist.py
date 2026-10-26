from dataclasses import dataclass
from typing import Protocol

from casero.accounts.domain.waitlist import WaitlistEntry, WaitlistSource
from casero.shared.kernel.clock import Clock
from casero.shared.kernel.ids import new_id


class WaitlistRepository(Protocol):
    async def add(self, entry: WaitlistEntry) -> None: ...


class WaitlistRateLimiter(Protocol):
    async def allow(self, client: str) -> bool: ...


@dataclass(frozen=True)
class JoinWaitlist:
    repository: WaitlistRepository
    limiter: WaitlistRateLimiter
    clock: Clock

    async def __call__(self, email: str, source: WaitlistSource, client: str) -> bool:
        if not await self.limiter.allow(client):
            return False
        now = self.clock.now()
        await self.repository.add(WaitlistEntry(new_id(), email.strip(), source, now, now))
        return True
