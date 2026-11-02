from collections.abc import Iterator
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine

from admin_client import admin_client
from casero.admin.api.protection import CONTENT_SECURITY_POLICY, MAX_BODY_BYTES
from database import Database

pytestmark = pytest.mark.anyio

EXPECTED_PROTECTION = {
    "content-security-policy": CONTENT_SECURITY_POLICY,
    "referrer-policy": "no-referrer",
    "x-content-type-options": "nosniff",
    "permissions-policy": "camera=(), microphone=(), geolocation=()",
    "x-robots-tag": "noindex",
    "cache-control": "no-store",
}


def protection_of(client: TestClient, path: str) -> dict[str, str]:
    headers = client.get(path).headers
    return {name: headers[name] for name in EXPECTED_PROTECTION}


async def test_the_panel_reaches_the_database_on_its_own_pool_as_casero_admin(
    database: Database,
) -> None:
    with admin_client(database) as client:
        answer = client.get("/api/admin/health")
        engine: AsyncEngine = cast(FastAPI, client.app).state.engine

    assert (answer.status_code, answer.json()) == (200, {"status": "ok"})
    assert engine.url.username == "casero_admin"


async def test_every_answer_carries_the_headers_caddy_would_add(database: Database) -> None:
    with admin_client(database) as client:
        served = protection_of(client, "/api/admin/health")
        missing = protection_of(client, "/api/admin/nothing-here")

    assert served == EXPECTED_PROTECTION
    assert missing == EXPECTED_PROTECTION


@pytest.mark.parametrize("path", ["/api/health", "/api/app/me", "/api/public/csrf", "/app", "/"])
async def test_the_panel_serves_nothing_of_the_public_app(database: Database, path: str) -> None:
    with admin_client(database) as client:
        assert client.get(path).status_code == 404


@pytest.mark.parametrize("path", ["/api/openapi.json", "/docs", "/redoc"])
async def test_the_panel_publishes_no_description_of_itself(database: Database, path: str) -> None:
    with admin_client(database) as client:
        assert client.get(path).status_code == 404


async def test_a_body_over_the_limit_is_refused_before_it_is_read(database: Database) -> None:
    with admin_client(database) as client:
        answer = client.post("/api/admin/health", content=b"x" * (MAX_BODY_BYTES + 1))

    assert answer.status_code == 413
    assert answer.headers["content-security-policy"] == CONTENT_SECURITY_POLICY


async def test_a_body_at_the_limit_goes_through_to_the_routes(database: Database) -> None:
    with admin_client(database) as client:
        answer = client.post("/api/admin/health", content=b"x" * MAX_BODY_BYTES)

    assert answer.status_code == 405


async def test_a_chunked_body_is_refused_because_its_size_is_unknown(database: Database) -> None:
    def chunks() -> Iterator[bytes]:
        yield b"x"

    with admin_client(database) as client:
        answer = client.post("/api/admin/health", content=chunks())

    assert answer.status_code == 411
    assert answer.headers["content-security-policy"] == CONTENT_SECURITY_POLICY
