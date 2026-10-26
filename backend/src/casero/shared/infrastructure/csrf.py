import hmac
import secrets

from fastapi import HTTPException, Request, Response

CSRF_COOKIE = "__Host-casero_csrf"
CSRF_HEADER = "X-CSRF-Token"
TOKEN_BYTES = 32


def issue_csrf_cookie(response: Response) -> None:
    """Double-submit token (ADR-0004): readable by the page, echoed in X-CSRF-Token."""
    response.set_cookie(
        CSRF_COOKIE,
        secrets.token_urlsafe(TOKEN_BYTES),
        secure=True,
        httponly=False,
        samesite="lax",
        path="/",
    )


async def require_csrf(request: Request) -> None:
    cookie = request.cookies.get(CSRF_COOKIE)
    header = request.headers.get(CSRF_HEADER)
    if not cookie or not header or not hmac.compare_digest(cookie, header):
        raise HTTPException(status_code=403, detail="csrf")
