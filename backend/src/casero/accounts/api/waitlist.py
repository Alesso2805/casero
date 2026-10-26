from collections.abc import Awaitable, Callable
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, EmailStr

from casero.accounts.application.waitlist import JoinWaitlist
from casero.accounts.domain.waitlist import WaitlistSource


class JoinWaitlistRequest(BaseModel):
    email: EmailStr
    source: WaitlistSource = "landing"
    consent: Literal[True]


def create_router(provide_join_waitlist: Callable[..., Awaitable[JoinWaitlist]]) -> APIRouter:
    router = APIRouter()

    @router.post(
        "/api/public/waitlist",
        status_code=202,
        responses={429: {"description": "Too many requests from this client"}},
    )
    async def join_waitlist(
        body: JoinWaitlistRequest,
        request: Request,
        join: Annotated[JoinWaitlist, Depends(provide_join_waitlist)],
    ) -> Response:
        """Add an email to the waitlist once the visitor has given consent."""
        client = request.client.host if request.client else "unknown"
        if not await join(str(body.email), body.source, client):
            return Response(status_code=429)
        return Response(status_code=202)

    return router
