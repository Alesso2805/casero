from datetime import timedelta

from fastapi import Response

SESSION_COOKIE = "__Host-casero_session"
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
