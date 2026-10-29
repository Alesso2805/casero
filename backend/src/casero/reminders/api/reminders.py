from collections.abc import Awaitable, Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from casero.accounts.application.context import AccountContext
from casero.reminders.application.reminders import PrepareReminder
from casero.reminders.domain.messages import TemplateKind
from casero.shared.infrastructure.csrf import require_csrf

REFUSAL_STATUS = {"lease_not_found": 404, "whatsapp_unavailable": 403, "nothing_due": 409}


class ReminderResponse(BaseModel):
    kind: TemplateKind
    charge_id: UUID
    message: str
    url: str


def create_router(
    current_account: Callable[..., Awaitable[AccountContext]],
    provide_prepare: Callable[..., Awaitable[PrepareReminder]],
) -> APIRouter:
    router = APIRouter()

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
