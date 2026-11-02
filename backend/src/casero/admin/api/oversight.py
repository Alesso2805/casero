from collections.abc import Awaitable, Callable
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from casero.admin.application.oversight import (
    DeadlineState,
    ViewComplaintDeadlines,
    ViewSchedule,
)
from casero.admin.domain.staff import StaffSession


class ScheduleEntryResponse(BaseModel):
    period: str
    ruc_group: str
    due_on: date
    source_url: str


class ComplaintDeadlineResponse(BaseModel):
    number: str
    kind: str
    filed_at: datetime
    due_on: date
    responded_at: datetime | None
    response_channel: str
    state: DeadlineState


def create_router(
    current_staff: Callable[..., Awaitable[StaffSession]],
    provide_schedule: Callable[..., Awaitable[ViewSchedule]],
    provide_complaints: Callable[..., Awaitable[ViewComplaintDeadlines]],
) -> APIRouter:
    router = APIRouter()

    @router.get(
        "/api/admin/sunat-schedule", responses={401: {"description": "No valid staff session"}}
    )
    async def schedule(
        session: Annotated[StaffSession, Depends(current_staff)],
        view: Annotated[ViewSchedule, Depends(provide_schedule)],
    ) -> list[ScheduleEntryResponse]:
        """The SUNAT schedule as loaded from the yearly files; the panel can't change it."""
        return [
            ScheduleEntryResponse(
                period=entry.period,
                ruc_group=entry.ruc_group,
                due_on=entry.due_on,
                source_url=entry.source_url,
            )
            for entry in await view(session.staff_id)
        ]

    @router.get("/api/admin/complaints", responses={401: {"description": "No valid staff session"}})
    async def complaints(
        session: Annotated[StaffSession, Depends(current_staff)],
        view: Annotated[ViewComplaintDeadlines, Depends(provide_complaints)],
    ) -> list[ComplaintDeadlineResponse]:
        """Complaints and their deadlines, without the consumer's data."""
        return [
            ComplaintDeadlineResponse(
                number=deadline.number,
                kind=deadline.kind,
                filed_at=deadline.filed_at,
                due_on=deadline.due_on,
                responded_at=deadline.responded_at,
                response_channel=deadline.response_channel,
                state=state,
            )
            for deadline, state in await view(session.staff_id)
        ]

    return router
