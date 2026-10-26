from collections.abc import Awaitable, Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from casero.identity.application.unsubscribe import Unsubscribe
from casero.identity.domain.email_suppressions import ScheduledEmailKind

MAX_TOKEN_LENGTH = 64


def create_router(provide_unsubscribe: Callable[..., Awaitable[Unsubscribe]]) -> APIRouter:
    router = APIRouter()

    @router.post(
        "/api/public/unsubscribe",
        status_code=204,
        responses={403: {"description": "The link is not valid"}},
    )
    async def unsubscribe(
        user_id: Annotated[UUID, Query(alias="u")],
        kind: Annotated[ScheduledEmailKind, Query(alias="k")],
        token: Annotated[str, Query(alias="t", max_length=MAX_TOKEN_LENGTH)],
        unsubscribe: Annotated[Unsubscribe, Depends(provide_unsubscribe)],
    ) -> Response:
        """Stop one kind of scheduled email: RFC 8058 one-click, also used by the /baja page."""
        if not await unsubscribe(user_id, kind, token):
            return Response(status_code=403)
        return Response(status_code=204)

    return router
