import zlib
from collections.abc import Iterator
from uuid import uuid7

import asyncpg
import pytest
from fastapi.testclient import TestClient

from casero.api import WAITLIST_JOINS_PER_HOUR, create_app
from casero.shared.infrastructure.settings import ApiSettings
from database import Database


@pytest.fixture
def client(database: Database, request: pytest.FixtureRequest) -> Iterator[TestClient]:
    url = database.dsn("casero_app").replace("postgresql://", "postgresql+asyncpg://", 1)
    app = create_app(ApiSettings(database_url=url, rate_limit_key=b"test-key"))
    address = f"198.51.100.{zlib.crc32(request.node.name.encode()) % 250 + 1}"
    with TestClient(app, client=(address, 50000)) as test_client:
        yield test_client


def unique_email() -> str:
    return f"{uuid7()}@example.com"


async def stored_emails(database: Database, email: str) -> int:
    owner = await asyncpg.connect(database.dsn("casero_owner"))
    try:
        count: int = await owner.fetchval(
            "SELECT count(*) FROM waitlist_entries WHERE lower(email) = lower($1)", email
        )
        return count
    finally:
        await owner.close()


@pytest.mark.anyio
async def test_a_consenting_visitor_joins_once(database: Database, client: TestClient) -> None:
    email = unique_email()

    first = client.post("/api/public/waitlist", json={"email": email, "consent": True})
    again = client.post("/api/public/waitlist", json={"email": email.upper(), "consent": True})

    assert first.status_code == 202
    assert again.status_code == 202
    assert await stored_emails(database, email) == 1


@pytest.mark.parametrize(
    "body",
    [
        {"email": "ana@example.com", "consent": False},
        {"email": "ana@example.com"},
        {"email": "no-es-un-correo", "consent": True},
        {"email": "ana@example.com", "consent": True, "source": "facebook"},
    ],
)
def test_invalid_requests_are_rejected(client: TestClient, body: dict[str, object]) -> None:
    response = client.post("/api/public/waitlist", json=body)

    assert response.status_code == 422


def test_a_client_is_limited_per_hour(client: TestClient) -> None:
    statuses = [
        client.post(
            "/api/public/waitlist", json={"email": unique_email(), "consent": True}
        ).status_code
        for _ in range(WAITLIST_JOINS_PER_HOUR + 1)
    ]

    assert statuses == [202] * WAITLIST_JOINS_PER_HOUR + [429]
