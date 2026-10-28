from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from fastapi import FastAPI
from starlette.types import Message

from casero.shared.infrastructure.database import Transaction, anonymous_transaction
from routes import api_routes, dependencies, offline_app

pytestmark = pytest.mark.anyio


class RecordingEngine:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    @asynccontextmanager
    async def begin(self) -> AsyncIterator[str]:
        yield "connection"
        self._events.append("commit")


async def test_a_write_commits_before_its_response_is_sent() -> None:
    events: list[str] = []
    app = FastAPI()
    app.state.engine = RecordingEngine(events)

    @app.post("/write", status_code=201)
    async def write(_: Transaction) -> dict[str, str]:
        return {}

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        if message["type"] == "http.response.start":
            events.append(f"response {message['status']}")

    scope: dict[str, Any] = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "https",
        "path": "/write",
        "raw_path": b"/write",
        "root_path": "",
        "query_string": b"",
        "headers": [],
        "client": ("203.0.113.1", 50000),
        "server": ("testserver", 443),
    }
    await app(scope, receive, send)

    assert events == ["commit", "response 201"]


def test_every_route_opens_its_transaction_with_the_same_early_scope() -> None:
    scopes = {
        dependency.scope
        for route in api_routes(offline_app().routes)
        for dependency in dependencies(route.dependant)
        if dependency.call is anonymous_transaction
    }

    assert scopes == {"function"}
