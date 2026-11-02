from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal, Protocol
from uuid import UUID

from casero.admin.application.complaint_commands import StaffActions
from casero.shared.kernel.clock import Clock

COMPLAINTS_SHOWN = 200
DeadlineState = Literal["answered", "open", "overdue"]


@dataclass(frozen=True)
class ScheduleEntry:
    period: str
    ruc_group: str
    due_on: date
    source_url: str


@dataclass(frozen=True)
class ComplaintDeadline:
    """Only what tells the deadline: the panel has no use for who filed it or what they said."""

    number: str
    kind: str
    filed_at: datetime
    due_on: date
    responded_at: datetime | None
    response_channel: str

    def state(self, today: date) -> DeadlineState:
        if self.responded_at is not None:
            return "answered"
        return "overdue" if today > self.due_on else "open"


class OversightRecords(Protocol):
    async def schedule(self) -> list[ScheduleEntry]: ...

    async def complaint_deadlines(self, limit: int) -> list[ComplaintDeadline]:
        """Unanswered first, the closest deadline on top; then the latest answered."""
        ...


@dataclass(frozen=True)
class ViewSchedule:
    records: OversightRecords
    actions: StaffActions
    clock: Clock

    async def __call__(self, staff_id: UUID) -> list[ScheduleEntry]:
        await self.actions.record(
            "schedule.view", "sunat_due_dates", None, self.clock.now(), staff_id
        )
        return await self.records.schedule()


@dataclass(frozen=True)
class ViewComplaintDeadlines:
    records: OversightRecords
    actions: StaffActions
    clock: Clock

    async def __call__(self, staff_id: UUID) -> list[tuple[ComplaintDeadline, DeadlineState]]:
        await self.actions.record("complaints.view", "complaints", None, self.clock.now(), staff_id)
        today = self.clock.today_lima()
        deadlines = await self.records.complaint_deadlines(COMPLAINTS_SHOWN)
        return [(deadline, deadline.state(today)) for deadline in deadlines]
