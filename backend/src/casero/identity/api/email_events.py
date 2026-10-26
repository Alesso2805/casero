import json
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from casero.identity.application.email_suppressions import RecordEmailEvent

MAX_SNS_MESSAGE_BYTES = 256 * 1024


def create_router(provide_record: Callable[..., Awaitable[RecordEmailEvent]]) -> APIRouter:
    router = APIRouter()

    @router.post(
        "/api/public/email-events",
        status_code=200,
        responses={
            400: {"description": "Not an SNS message"},
            403: {"description": "Wrong topic or invalid signature"},
        },
    )
    async def receive_email_event(
        request: Request,
        record: Annotated[RecordEmailEvent, Depends(provide_record)],
    ) -> Response:
        """Receive SES bounces and complaints through an SNS subscription."""
        body = await request.body()
        if len(body) > MAX_SNS_MESSAGE_BYTES:
            return Response(status_code=400)
        try:
            message = json.loads(body)
        except json.JSONDecodeError:
            return Response(status_code=400)
        if not isinstance(message, dict):
            return Response(status_code=400)
        outcome = await record(message)
        return Response(status_code=403 if outcome == "rejected" else 200)

    return router
