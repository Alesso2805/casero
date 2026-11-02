from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; "
    "form-action 'self'; frame-ancestors 'none'"
)
SECURITY_HEADERS = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "X-Robots-Tag": "noindex",
}
MAX_BODY_BYTES = 64 * 1024


class AdminProtection:
    """What Caddy gives the public site, since Caddy isn't in front of this listener (ADR-0008)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def protected(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message).update(SECURITY_HEADERS)
            await send(message)

        headers = Headers(scope=scope)
        # Uvicorn reads no more than a declared length, so only a chunked body could run long.
        if "transfer-encoding" in headers:
            await Response(status_code=411)(scope, receive, protected)
        elif int(headers.get("content-length", "0")) > MAX_BODY_BYTES:
            await Response(status_code=413)(scope, receive, protected)
        else:
            await self.app(scope, receive, protected)
