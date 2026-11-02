from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field, StringConstraints

from casero.admin.application.staff_sessions import AuthenticateStaff, LogStaffIn, LogStaffOut
from casero.admin.domain.staff import STAFF_SESSION_LIFETIME, StaffSession
from casero.shared.infrastructure.csrf import issue_csrf_cookie, require_csrf
from casero.shared.infrastructure.session_cookie import (
    STAFF_COOKIE,
    clear_staff_cookie,
    set_staff_cookie,
)

MAX_PASSWORD_LENGTH = 1024
MAX_CODE_LENGTH = 64


class StaffLoginRequest(BaseModel):
    email: EmailStr
    password: Annotated[str, Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)]
    code: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_CODE_LENGTH)
    ]


class StaffResponse(BaseModel):
    email: str


def staff_dependency(
    provide_authenticate: Callable[..., Awaitable[AuthenticateStaff]],
) -> Callable[..., Awaitable[StaffSession]]:
    async def current_staff(
        request: Request,
        authenticate: Annotated[AuthenticateStaff, Depends(provide_authenticate)],
    ) -> StaffSession:
        token = request.cookies.get(STAFF_COOKIE)
        session = await authenticate(token) if token else None
        if session is None:
            raise HTTPException(status_code=401, detail="no_session")
        return session

    return current_staff


def create_router(
    provide_log_in: Callable[..., Awaitable[LogStaffIn]],
    provide_log_out: Callable[..., Awaitable[LogStaffOut]],
    current_staff: Callable[..., Awaitable[StaffSession]],
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/admin/csrf", status_code=204)
    def issue_csrf() -> Response:
        """Set the CSRF cookie that every unsafe request, login included, must echo."""
        response = Response(status_code=204)
        issue_csrf_cookie(response)
        return response

    @router.post(
        "/api/admin/session",
        status_code=204,
        dependencies=[Depends(require_csrf)],
        responses={401: {"description": "Wrong email, password or code"}},
    )
    async def log_in(
        body: StaffLoginRequest,
        log_in: Annotated[LogStaffIn, Depends(provide_log_in)],
    ) -> Response:
        """Start a staff session, closing any earlier one."""
        token = await log_in(str(body.email), body.password, body.code)
        if token is None:
            return Response(status_code=401)
        response = Response(status_code=204)
        set_staff_cookie(response, token, STAFF_SESSION_LIFETIME)
        issue_csrf_cookie(response)
        return response

    @router.delete("/api/admin/session", status_code=204, dependencies=[Depends(require_csrf)])
    async def log_out(
        session: Annotated[StaffSession, Depends(current_staff)],
        log_out: Annotated[LogStaffOut, Depends(provide_log_out)],
    ) -> Response:
        """End this staff session."""
        await log_out(session)
        response = Response(status_code=204)
        clear_staff_cookie(response)
        return response

    @router.get("/api/admin/me", responses={401: {"description": "No valid staff session"}})
    async def me(session: Annotated[StaffSession, Depends(current_staff)]) -> StaffResponse:
        """Who is signed in to the panel."""
        return StaffResponse(email=session.email)

    return router
