from collections.abc import Awaitable, Callable
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, EmailStr, Field, StringConstraints

from casero.accounts.application.registration import (
    Registered,
    RegisterLandlord,
    Registration,
)
from casero.identity.application.users import MIN_PASSWORD_LENGTH
from casero.shared.infrastructure.csrf import issue_csrf_cookie, require_csrf
from casero.shared.infrastructure.session_cookie import SESSION_COOKIE, set_session_cookie

MAX_PASSWORD_LENGTH = 1024
MAX_INVITE_TOKEN_LENGTH = 64

DisplayName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]

STATUS = {
    "closed": 403,
    "invite_invalid": 403,
    "limited": 429,
    "email_taken": 409,
    "weak_password": 422,
}


class RegistrationRequest(BaseModel):
    email: EmailStr
    password: Annotated[str, Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)]
    display_name: DisplayName
    invite_token: Annotated[str, Field(max_length=MAX_INVITE_TOKEN_LENGTH)] | None = None
    accept_terms_and_privacy: Literal[True]
    consent_sensitive_data: Literal[True]


def create_router(provide_register: Callable[..., Awaitable[RegisterLandlord]]) -> APIRouter:
    router = APIRouter()

    @router.post(
        "/api/public/registration",
        status_code=201,
        dependencies=[Depends(require_csrf)],
        responses={
            403: {"description": "Registration is closed or the invitation is not valid"},
            409: {"description": "That email already has an account"},
            429: {"description": "Too many attempts from this client"},
        },
    )
    async def register(
        body: RegistrationRequest,
        request: Request,
        register: Annotated[RegisterLandlord, Depends(provide_register)],
    ) -> Response:
        """Create a landlord account, record the legal acceptances and start a session."""
        client = request.client.host if request.client else "unknown"
        outcome = await register(
            Registration(
                email=str(body.email),
                password=body.password,
                display_name=body.display_name,
                invite_token=body.invite_token,
                client=client,
                previous_token=request.cookies.get(SESSION_COOKIE),
            )
        )
        if not isinstance(outcome, Registered):
            return Response(status_code=STATUS[outcome])
        response = Response(status_code=201)
        set_session_cookie(response, outcome.login.token)
        issue_csrf_cookie(response)
        return response

    return router
