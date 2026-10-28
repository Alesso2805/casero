from datetime import UTC, datetime

import pytest

from api_client import FixedClock, address_for, api_client
from database import Database

pytestmark = pytest.mark.anyio


async def test_health_answers_ok_when_the_database_does(
    database: Database, request: pytest.FixtureRequest
) -> None:
    clock = FixedClock(datetime(2026, 10, 28, 15, 0, tzinfo=UTC))
    with api_client(database, address_for(request.node.name), clock) as client:
        response = client.get("/api/health")

    assert (response.status_code, response.json()) == (200, {"status": "ok"})
