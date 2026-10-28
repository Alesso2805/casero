import structlog
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from structlog.typing import EventDict, WrappedLogger

from casero.shared.infrastructure.error_tracking import REPORTED, forward_errors, report_exception

# A safety net for rule 8 (ADR-0007): code must not log these, and if it does they are dropped.
PERSONAL_KEYS = frozenset(
    {
        "address",
        "amount_cents",
        "display_name",
        "document",
        "document_number",
        "email",
        "full_name",
        "password",
        "phone",
        "phone_e164",
        "ruc",
        "token",
    }
)

log = structlog.get_logger()


def drop_personal_fields(_: WrappedLogger, __: str, event: EventDict) -> EventDict:
    for key in PERSONAL_KEYS & event.keys():
        del event[key]
    return event


def configure_logging() -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            drop_personal_fields,
            forward_errors,
            structlog.processors.JSONRenderer(),
        ]
    )


class ErrorShield:
    """Answers 500 to unhandled errors and logs only their type.

    Starlette re-raises them so Uvicorn logs the traceback, and database errors quote the
    offending values, personal data included (rule 8).
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def tracked(message: Message) -> None:
            nonlocal started
            started = started or message["type"] == "http.response.start"
            await send(message)

        try:
            await self.app(scope, receive, tracked)
        except Exception as error:
            report_exception(error)
            log.error("api.unhandled_error", error=type(error).__name__, **{REPORTED: True})
            if not started:
                response = JSONResponse({"detail": "internal_error"}, status_code=500)
                await response(scope, receive, send)
