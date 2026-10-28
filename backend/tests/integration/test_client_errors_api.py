from collections.abc import Iterator
from typing import Any

import pytest
import sentry_sdk
from sentry_sdk.envelope import Envelope
from sentry_sdk.transport import Transport

from api_client import address_for, api_client
from casero.api import CLIENT_ERRORS_PER_HOUR
from casero.shared.infrastructure.error_tracking import init_error_tracking
from database import Database

REPORT = {"name": "TypeError", "route": "/app/contratos", "where": "/assets/index-abc.js:1:2048"}


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
    yield transport
    sentry_sdk.get_global_scope().set_client(None)


def test_a_browser_error_reaches_error_tracking_by_type_and_route(
    database: Database, request: pytest.FixtureRequest, sentry: Recording
) -> None:
    with api_client(database, address_for(request.node.name)) as client:
        init_error_tracking("https://public@example.invalid/1", "test", sentry)
        response = client.post("/api/public/client-errors", json=REPORT)
        sentry_sdk.flush()

    assert response.status_code == 204
    [event] = sentry.events
    assert event["message"] == "web.unhandled_error"
    assert event["tags"] == {
        "error": "TypeError",
        "route": "/app/contratos",
        "where": "/assets/index-abc.js:1:2048",
    }


@pytest.mark.parametrize(
    "report",
    [
        {**REPORT, "route": "/i?t=secret"},
        {**REPORT, "route": "/i#t=secret"},
        {**REPORT, "where": "https://casero.example/assets/x.js?token=1"},
        {**REPORT, "name": "<script>"},
        {**REPORT, "route": "app"},
    ],
)
def test_reports_that_could_carry_tokens_are_refused(
    database: Database, request: pytest.FixtureRequest, report: dict[str, str]
) -> None:
    with api_client(database, address_for(request.node.name)) as client:
        assert client.post("/api/public/client-errors", json=report).status_code == 422


def test_reports_are_rate_limited(database: Database, request: pytest.FixtureRequest) -> None:
    with api_client(database, address_for(request.node.name)) as client:
        statuses = [
            client.post("/api/public/client-errors", json=REPORT).status_code
            for _ in range(CLIENT_ERRORS_PER_HOUR + 1)
        ]

    assert statuses[:-1] == [204] * CLIENT_ERRORS_PER_HOUR
    assert statuses[-1] == 429
