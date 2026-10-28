from typing import Any

import sentry_sdk
from sentry_sdk.transport import Transport
from sentry_sdk.types import Event, Hint
from structlog.typing import EventDict, WrappedLogger

# Set by a caller that already sent the error to Sentry with its stack trace.
REPORTED = "reported"


def scrub(event: Event, _: Hint) -> Event:
    """Keeps only what points at the code: no request data, user, breadcrumbs or messages.

    Exception messages and local variables can quote personal data (rule 8, ADR-0011).
    """
    request = event.get("request")
    if request:
        url = str(request.get("url", "")).split("?", 1)[0]
        event["request"] = {"method": request.get("method"), "url": url}
    for key in ("user", "breadcrumbs", "extra"):
        event.pop(key, None)  # type: ignore[misc]
    for exception in event.get("exception", {}).get("values", []):
        exception["value"] = ""
        for frame in exception.get("stacktrace", {}).get("frames", []):
            frame.pop("vars", None)
    return event


def init_error_tracking(
    dsn: str | None, environment: str, transport: Transport | None = None
) -> None:
    """Turns on Sentry only when a DSN is configured; locally and in CI it stays off."""
    if not dsn:
        return
    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        include_local_variables=False,
        max_breadcrumbs=0,
        traces_sample_rate=0,
        before_send=scrub,
        transport=transport,
    )


def forward_errors(_: WrappedLogger, __: str, event: EventDict) -> EventDict:
    """Sends error-level log events to Sentry as messages tagged with their safe fields."""
    if event.get("level") == "error" and not event.get(REPORTED) and sentry_sdk.is_initialized():
        tags: dict[str, Any] = {
            key: str(value) for key, value in event.items() if key not in {"event", "level"}
        }
        sentry_sdk.capture_message(str(event["event"]), level="error", tags=tags)
    return event


def report_exception(error: BaseException) -> None:
    if sentry_sdk.is_initialized():
        sentry_sdk.capture_exception(error)
