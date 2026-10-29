from collections.abc import Awaitable, Callable
from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from casero.accounts.application.context import AccountContext
from casero.reminders.application.reminders import ListLastReminders, PrepareReminder
from casero.reminders.domain.messages import TemplateKind
from casero.shared.infrastructure.csrf import require_csrf

REFUSAL_STATUS = {"lease_not_found": 404, "whatsapp_unavailable": 403, "nothing_due": 409}


class LastReminderResponse(BaseModel):
    lease_id: UUID
    sent_on: date
    days_ago: int


class ReminderResponse(BaseModel):
    kind: TemplateKind
    charge_id: UUID
    message: str
    url: str


def create_router(
    current_account: Callable[..., Awaitable[AccountContext]],
    provide_prepare: Callable[..., Awaitable[PrepareReminder]],
    provide_last: Callable[..., Awaitable[ListLastReminders]],
) -> APIRouter:
    router = APIRouter()

    @router.get(
        "/api/app/whatsapp-reminders",
        responses={
            401: {"description": "No valid session"},
            403: {"description": "No account, or the email is unverified past its deadline"},
        },
    )
    async def last_reminders(
        _: Annotated[AccountContext, Depends(current_account)],
        list_last: Annotated[ListLastReminders, Depends(provide_last)],
    ) -> list[LastReminderResponse]:
        """When each lease was last reminded, for "recordado hace N días"."""
        return [
            LastReminderResponse(lease_id=r.lease_id, sent_on=r.sent_on, days_ago=r.days_ago)
            for r in await list_last()
        ]

    @router.post(
        "/api/app/leases/{lease_id}/whatsapp-reminders",
        status_code=201,
        dependencies=[Depends(require_csrf)],
        responses={
            401: {"description": "No valid session"},
            403: {
                "description": "No account, unverified email past its deadline, `csrf`, or"
                " `whatsapp_unavailable` (plan or lease without WhatsApp)"
            },
            404: {"description": "`lease_not_found`"},
            409: {"description": "`nothing_due`: no unpaid rent to remind"},
        },
    )
    async def prepare_reminder(
        lease_id: UUID,
        context: Annotated[AccountContext, Depends(current_account)],
        prepare: Annotated[PrepareReminder, Depends(provide_prepare)],
    ) -> ReminderResponse:
        """The WhatsApp link with the message for the most urgent unpaid rent; logs the send."""
        result = await prepare(context, lease_id)
        if isinstance(result, str):
            raise HTTPException(status_code=REFUSAL_STATUS[result], detail=result)
        return ReminderResponse(
            kind=result.kind, charge_id=result.charge_id, message=result.message, url=result.url
        )

    return router
