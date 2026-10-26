from dataclasses import dataclass
from datetime import date
from typing import Protocol

from casero.admin.domain.complaints import (
    RESPONSE_BUSINESS_DAYS,
    Complaint,
    ComplaintSheet,
    add_business_days,
    complaint_number,
)
from casero.shared.kernel.clock import Clock
from casero.shared.kernel.ids import new_id


class ComplaintRepository(Protocol):
    async def next_sequence(self, year: int) -> int: ...

    async def holidays_after(self, day: date) -> frozenset[date]: ...

    async def add(self, complaint: Complaint) -> None: ...


class ComplaintRateLimiter(Protocol):
    async def allow(self, client: str) -> bool: ...


@dataclass(frozen=True)
class FileComplaint:
    repository: ComplaintRepository
    limiter: ComplaintRateLimiter
    clock: Clock

    async def __call__(self, sheet: ComplaintSheet, client: str) -> Complaint | None:
        if not await self.limiter.allow(client):
            return None
        filed_on = self.clock.today_lima()
        sequence = await self.repository.next_sequence(filed_on.year)
        holidays = await self.repository.holidays_after(filed_on)
        complaint = Complaint(
            id=new_id(),
            number=complaint_number(sequence, filed_on.year),
            created_at=self.clock.now(),
            due_on=add_business_days(filed_on, RESPONSE_BUSINESS_DAYS, holidays),
            sheet=sheet,
        )
        await self.repository.add(complaint)
        return complaint
