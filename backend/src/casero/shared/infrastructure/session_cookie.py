from datetime import timedelta

from fastapi import Response

SESSION_COOKIE = "__Host-casero_session"
STAFF_COOKIE = "__Host-casero_staff"
# Browsers cap cookies at 400 days; the server enforces the 30-day sliding expiry (ADR-0004).
SESSION_COOKIE_MAX_AGE = timedelta(days=400) // timedelta(seconds=1)


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_COOKIE_MAX_AGE,
        secure=True,
        httponly=True,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, secure=True, httponly=True, samesite="lax", path="/")


def set_staff_cookie(response: Response, token: str, lifetime: timedelta) -> None:
    response.set_cookie(
        STAFF_COOKIE,
        token,
        max_age=lifetime // timedelta(seconds=1),
        secure=True,
        httponly=True,
        samesite="strict",
        path="/",
    )


def clear_staff_cookie(response: Response) -> None:
    response.delete_cookie(STAFF_COOKIE, secure=True, httponly=True, samesite="strict", path="/")
