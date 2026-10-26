from datetime import UTC, date, datetime

import pytest

from casero.accounts.application.waitlist import JoinWaitlist
from casero.accounts.domain.waitlist import WaitlistEntry

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 25, 15, 30, tzinfo=UTC)


class FixedClock:
    def now(self) -> datetime:
        return NOW

    def today_lima(self) -> date:
        return date(2026, 10, 25)


class MemoryRepository:
    def __init__(self) -> None:
        self.entries: list[WaitlistEntry] = []

    async def add(self, entry: WaitlistEntry) -> None:
        self.entries.append(entry)


class Limiter:
    def __init__(self, allowed: bool) -> None:
        self.allowed = allowed
        self.clients: list[str] = []

    async def allow(self, client: str) -> bool:
        self.clients.append(client)
        return self.allowed


async def test_joining_records_the_consent_time_and_trims_the_email() -> None:
    repository = MemoryRepository()
    join = JoinWaitlist(repository, Limiter(allowed=True), FixedClock())

    assert await join("  ana@example.test ", "landing", "203.0.113.7")

    [entry] = repository.entries
    assert entry.email == "ana@example.test"
    assert entry.source == "landing"
    assert entry.consented_at == NOW
    assert entry.created_at == NOW


async def test_a_limited_client_is_not_added() -> None:
    repository = MemoryRepository()
    limiter = Limiter(allowed=False)
    join = JoinWaitlist(repository, limiter, FixedClock())

    assert not await join("ana@example.test", "landing", "203.0.113.7")

    assert repository.entries == []
    assert limiter.clients == ["203.0.113.7"]
