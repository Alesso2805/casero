from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field

from casero.identity.application.sessions import AuthenticateSession, LogIn, LogOut
from casero.identity.domain.account_emails import access_blocked, verify_by
from casero.identity.domain.sessions import Session
from casero.identity.infrastructure.sessions import SqlCredentials
from casero.shared.infrastructure.csrf import issue_csrf_cookie, require_csrf
from casero.shared.infrastructure.session_cookie import (
    SESSION_COOKIE,
    clear_session_cookie,
    set_session_cookie,
)
from casero.shared.kernel.clock import Clock

MAX_PASSWORD_LENGTH = 1024


class LoginRequest(BaseModel):
    email: EmailStr
    password: Annotated[str, Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)]


class MeResponse(BaseModel):
    user_id: UUID
    email: str
    email_verified: bool
    verify_by: datetime | None
    blocked_until_verified: bool


def session_dependency(
    provide_authenticate: Callable[..., Awaitable[AuthenticateSession]],
) -> Callable[..., Awaitable[Session]]:
    async def current_session(
        request: Request,
        authenticate: Annotated[AuthenticateSession, Depends(provide_authenticate)],
    ) -> Session:
        token = request.cookies.get(SESSION_COOKIE)
        session = await authenticate(token) if token else None
        if session is None:
            raise HTTPException(status_code=401, detail="no_session")
        return session

    return current_session


def create_router(
    provide_login: Callable[..., Awaitable[LogIn]],
    provide_logout: Callable[..., Awaitable[LogOut]],
    provide_credentials: Callable[..., Awaitable[SqlCredentials]],
    current_session: Callable[..., Awaitable[Session]],
    clock: Clock,
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/public/csrf", status_code=204)
    def issue_csrf() -> Response:
        """Set the CSRF cookie that every unsafe request, login included, must echo."""
        response = Response(status_code=204)
        issue_csrf_cookie(response)
        return response

    @router.post(
        "/api/public/session",
        status_code=204,
        dependencies=[Depends(require_csrf)],
        responses={
            401: {"description": "Wrong email or password"},
            429: {"description": "Too many attempts from this client"},
        },
    )
    async def log_in(
        body: LoginRequest,
        request: Request,
        log_in: Annotated[LogIn, Depends(provide_login)],
    ) -> Response:
        """Start a session; a new session token replaces any previous one."""
        client = request.client.host if request.client else "unknown"
        outcome = await log_in(
            str(body.email), body.password, client, request.cookies.get(SESSION_COOKIE)
        )
        if outcome == "limited":
            return Response(status_code=429)
        if outcome == "invalid":
            return Response(status_code=401)
        response = Response(status_code=204)
        set_session_cookie(response, outcome.token)
        issue_csrf_cookie(response)
        return response

    @router.delete("/api/app/session", status_code=204, dependencies=[Depends(require_csrf)])
    async def log_out(
        session: Annotated[Session, Depends(current_session)],
        log_out: Annotated[LogOut, Depends(provide_logout)],
    ) -> Response:
        """End this session."""
        await log_out(session, everywhere=False)
        response = Response(status_code=204)
        clear_session_cookie(response)
        return response

    @router.delete("/api/app/sessions", status_code=204, dependencies=[Depends(require_csrf)])
    async def log_out_everywhere(
        session: Annotated[Session, Depends(current_session)],
        log_out: Annotated[LogOut, Depends(provide_logout)],
    ) -> Response:
        """End every session of this user, on every device."""
        await log_out(session, everywhere=True)
        response = Response(status_code=204)
        clear_session_cookie(response)
        return response

    @router.get("/api/app/me", responses={401: {"description": "No valid session"}})
    async def me(
        session: Annotated[Session, Depends(current_session)],
        credentials: Annotated[SqlCredentials, Depends(provide_credentials)],
    ) -> MeResponse:
        """Who is signed in."""
        profile = await credentials.profile(session.user_id)
        if profile is None:
            raise HTTPException(status_code=401, detail="no_session")
        return MeResponse(
            user_id=session.user_id,
            email=profile.email,
            email_verified=profile.email_verified,
            verify_by=verify_by(profile.created_at, profile.email_verified),
            blocked_until_verified=access_blocked(
                profile.created_at, profile.email_verified, clock.now()
            ),
        )

    return router
