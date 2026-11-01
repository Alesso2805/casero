from collections.abc import Awaitable, Callable
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from casero.accounts.application.context import AccountContext
from casero.accounts.application.deletion import CancelDeletion, RequestDeletion
from casero.shared.infrastructure.csrf import require_csrf
from casero.shared.infrastructure.session_cookie import clear_session_cookie

MAX_TOKEN_LENGTH = 128


class DeletionResponse(BaseModel):
    purge_on: date = Field(description="The day the data is deleted for good")


class CancelDeletionRequest(BaseModel):
    token: Annotated[str, Field(min_length=1, max_length=MAX_TOKEN_LENGTH)]


def create_router(
    account_for_rights: Callable[..., Awaitable[AccountContext]],
    provide_request: Callable[..., Awaitable[RequestDeletion]],
    provide_cancel: Callable[..., Awaitable[CancelDeletion]],
) -> APIRouter:
    router = APIRouter()

    @router.post(
        "/api/app/account/deletion",
        dependencies=[Depends(require_csrf)],
        responses={
            401: {"description": "No valid session"},
            403: {"description": "No account, unverified email, or `csrf`"},
            409: {"description": "The deletion was already requested"},
            503: {"description": "The cancellation email could not be sent; nothing changed"},
        },
    )
    async def request_deletion(
        response: Response,
        context: Annotated[AccountContext, Depends(account_for_rights)],
        request: Annotated[RequestDeletion, Depends(provide_request)],
    ) -> DeletionResponse:
        """Anonymize the user, close every session and schedule the purge."""
        result = await request(context)
        if result == "already_requested":
            raise HTTPException(status_code=409, detail=result)
        if result == "email_failed":
            raise HTTPException(status_code=503, detail=result)
        clear_session_cookie(response)
        return DeletionResponse(purge_on=result)

    @router.post(
        "/api/public/account-deletion/cancellation",
        status_code=204,
        responses={
            400: {"description": "The link is invalid, used or expired"},
            409: {"description": "`email_taken`: that email has another account now"},
        },
    )
    async def cancel_deletion(
        body: CancelDeletionRequest,
        cancel: Annotated[CancelDeletion, Depends(provide_cancel)],
    ) -> Response:
        """Cancel a scheduled deletion with the token from the emailed link."""
        result = await cancel(body.token)
        if result == "invalid":
            return Response(status_code=400)
        if result == "email_taken":
            raise HTTPException(status_code=409, detail=result)
        return Response(status_code=204)

    return router
