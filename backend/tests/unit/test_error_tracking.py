import logging
from collections.abc import Iterator
from typing import Any

import pytest
import sentry_sdk
import structlog
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sentry_sdk.envelope import Envelope
from sentry_sdk.transport import Transport

from casero.shared.infrastructure.error_tracking import init_error_tracking, scrub
from casero.shared.infrastructure.logs import ErrorShield, configure_logging

PERSONAL = "ana.quispe@example.com"


class Recording(Transport):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[dict[str, Any]] = []

    def capture_envelope(self, envelope: Envelope) -> None:
        for item in envelope.items:
            if item.type == "event" and item.payload.json is not None:
                self.events.append(item.payload.json)


@pytest.fixture
def sentry() -> Iterator[Recording]:
    transport = Recording()
    init_error_tracking("https://public@example.invalid/1", "test", transport)
    yield transport
    sentry_sdk.get_global_scope().set_client(None)


def test_without_a_dsn_sentry_is_never_started(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[object] = []
    monkeypatch.setattr(sentry_sdk, "init", lambda *args, **kwargs: calls.append(kwargs))

    init_error_tracking(None, "test")
    init_error_tracking("", "test")

    assert calls == []


def test_events_keep_only_what_points_at_the_code() -> None:
    event: Any = {
        "request": {
            "method": "POST",
            "url": "https://casero.example/api/app/renters?token=x",
            "headers": {"Cookie": "__Host-casero_session=s"},
            "data": {"full_name": "Ana"},
            "query_string": "token=x",
        },
        "user": {"email": PERSONAL},
        "breadcrumbs": {"values": [{"message": PERSONAL}]},
        "extra": {"email": PERSONAL},
        "exception": {
            "values": [
                {
                    "type": "IntegrityError",
                    "value": f"Key (email)=({PERSONAL})",
                    "stacktrace": {"frames": [{"function": "add", "vars": {"email": PERSONAL}}]},
                }
            ]
        },
    }

    scrubbed = scrub(event, {})

    assert PERSONAL not in repr(scrubbed)
    assert scrubbed["request"] == {
        "method": "POST",
        "url": "https://casero.example/api/app/renters",
    }
    assert scrubbed["exception"]["values"][0]["type"] == "IntegrityError"
    assert scrubbed["exception"]["values"][0]["stacktrace"]["frames"] == [{"function": "add"}]


def test_an_unhandled_api_error_is_sent_once_with_its_type_and_stack(sentry: Recording) -> None:
    app = FastAPI()
    app.add_middleware(ErrorShield)

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError(f"Key (email)=({PERSONAL})")

    with TestClient(app) as client:
        assert client.get("/boom").status_code == 500
    sentry_sdk.flush()

    [event] = sentry.events
    [exception] = event["exception"]["values"]
    assert (exception["type"], exception["value"]) == ("RuntimeError", "")
    assert exception["stacktrace"]["frames"]
    assert PERSONAL not in repr(event)


def test_error_logs_reach_error_tracking_as_tagged_messages(sentry: Recording) -> None:
    configure_logging()

    structlog.get_logger().error("worker.job_crashed", job="rent_charges", error="KeyError")
    structlog.get_logger().info("worker.started")
    sentry_sdk.flush()

    [event] = sentry.events
    assert event["message"] == "worker.job_crashed"
    assert event["tags"] == {"job": "rent_charges", "error": "KeyError"}


def test_library_log_records_never_reach_error_tracking(sentry: Recording) -> None:
    logging.getLogger("asyncpg.pool").error("bad value %s for renter", PERSONAL)
    sentry_sdk.flush()

    assert sentry.events == []
