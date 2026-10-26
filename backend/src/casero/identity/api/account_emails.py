from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, EmailStr, Field

from casero.identity.application.account_emails import (
    ConfirmEmail,
    RequestPasswordReset,
    ResetPassword,
    SendVerification,
)
from casero.identity.domain.sessions import MIN_PASSWORD_LENGTH, Session
from casero.shared.infrastructure.csrf import require_csrf

MAX_TOKEN_LENGTH = 64
MAX_PASSWORD_LENGTH = 1024

Token = Annotated[str, Field(min_length=1, max_length=MAX_TOKEN_LENGTH)]

SEND_STATUS = {"sent": 202, "verified": 204, "limited": 429, "suppressed": 422, "failed": 503}


class TokenRequest(BaseModel):
    token: Token


class ResetRequest(BaseModel):
    email: EmailStr


class NewPasswordRequest(BaseModel):
    token: Token
    password: Annotated[str, Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)]


def create_router(
    current_session: Callable[..., Awaitable[Session]],
    provide_send_verification: Callable[..., Awaitable[SendVerification]],
    provide_confirm_email: Callable[..., Awaitable[ConfirmEmail]],
    provide_request_reset: Callable[..., Awaitable[RequestPasswordReset]],
    provide_reset_password: Callable[..., Awaitable[ResetPassword]],
) -> APIRouter:
    router = APIRouter()

    @router.post(
        "/api/app/email-verification",
        status_code=202,
        dependencies=[Depends(require_csrf)],
        responses={
            204: {"description": "The email is already verified"},
            422: {"description": "The address bounced or complained; it gets no email"},
            429: {"description": "Three verification emails per hour at most"},
            503: {"description": "The email could not be sent"},
        },
    )
    async def send_verification(
        session: Annotated[Session, Depends(current_session)],
        send: Annotated[SendVerification, Depends(provide_send_verification)],
    ) -> Response:
        """Send a new email-verification link."""
        return Response(status_code=SEND_STATUS[await send(session.user_id)])

    @router.post(
        "/api/public/email-verification",
        status_code=204,
        responses={400: {"description": "The link is invalid, used or expired"}},
    )
    async def confirm_email(
        body: TokenRequest, confirm: Annotated[ConfirmEmail, Depends(provide_confirm_email)]
    ) -> Response:
        """Confirm an email with the token from the verification link."""
        return Response(status_code=204 if await confirm(body.token) else 400)

    @router.post(
        "/api/public/password-reset",
        status_code=202,
        responses={429: {"description": "Too many requests from this client"}},
    )
    async def request_reset(
        body: ResetRequest,
        request: Request,
        reset: Annotated[RequestPasswordReset, Depends(provide_request_reset)],
    ) -> Response:
        """Email a password-reset link if the address has an account; the answer is the same."""
        client = request.client.host if request.client else "unknown"
        outcome = await reset(str(body.email), client)
        return Response(status_code=429 if outcome == "limited" else 202)

    @router.post(
        "/api/public/password-reset/confirm",
        status_code=204,
        responses={400: {"description": "The link is invalid, used or expired"}},
    )
    async def reset_password(
        body: NewPasswordRequest,
        reset: Annotated[ResetPassword, Depends(provide_reset_password)],
    ) -> Response:
        """Set a new password with the token from the reset link and close every session."""
        outcome = await reset(body.token, body.password)
        return Response(status_code={"done": 204, "invalid": 400, "weak": 422}[outcome])

    return router
