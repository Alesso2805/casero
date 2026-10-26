from datetime import UTC, datetime, timedelta

import asyncpg
import pytest

from api_client import FixedClock, address_for, api_client
from casero.api import CALCULATIONS_PER_HOUR
from casero.shared.infrastructure.database import create_engine
from casero.shared.infrastructure.rate_limits import purge_expired_buckets
from database import Database

pytestmark = pytest.mark.anyio

CALCULATOR = "/api/public/tax-calculator"


def calculate(database: Database, name: str, body: dict[str, object]) -> tuple[int, object]:
    with api_client(database, address_for(name)) as client:
        response = client.post(CALCULATOR, json=body)
    return response.status_code, response.json() if response.content else None


def test_it_uses_the_loaded_2026_rules_and_schedule(
    database: Database, request: pytest.FixtureRequest
) -> None:
    status, body = calculate(
        database,
        request.node.name,
        {"period": "2026-03", "collected_cents": [55100, 54950], "ruc_group": "0"},
    )

    assert status == 200
    assert body == {
        "period": "2026-03",
        "rate_bp": 625,
        "deduction_bp": 2000,
        "lines": [
            {"collected_cents": 55100, "base_cents": 55100, "tax_cents": 2800},
            {"collected_cents": 54950, "base_cents": 55000, "tax_cents": 2800},
        ],
        "total_tax_cents": 5600,
        "due_on": "2026-04-17",
    }


def test_without_a_ruc_group_there_is_no_due_date(
    database: Database, request: pytest.FixtureRequest
) -> None:
    status, body = calculate(
        database, request.node.name, {"period": "2026-12", "collected_cents": [100000]}
    )

    assert status == 200
    assert isinstance(body, dict)
    assert body["due_on"] is None


def test_a_year_without_rules_is_not_found(
    database: Database, request: pytest.FixtureRequest
) -> None:
    status, _ = calculate(
        database, request.node.name, {"period": "2025-12", "collected_cents": [100000]}
    )

    assert status == 404


@pytest.mark.parametrize(
    "body",
    [
        {"period": "2026-13", "collected_cents": [100]},
        {"period": "2026-03", "collected_cents": []},
        {"period": "2026-03", "collected_cents": [100] * 21},
        {"period": "2026-03", "collected_cents": [-1]},
        {"period": "2026-03", "collected_cents": [10.5]},
        {"period": "2026-03", "collected_cents": [100], "ruc_group": "2"},
    ],
)
def test_invalid_requests_are_rejected(
    database: Database, request: pytest.FixtureRequest, body: dict[str, object]
) -> None:
    assert calculate(database, request.node.name, body)[0] == 422


def test_a_client_is_limited_per_hour(database: Database, request: pytest.FixtureRequest) -> None:
    clock = FixedClock(datetime(2046, 3, 4, 15, 0, tzinfo=UTC))
    body = {"period": "2026-03", "collected_cents": [100]}

    with api_client(database, address_for(request.node.name), clock) as client:
        statuses = [
            client.post(CALCULATOR, json=body).status_code for _ in range(CALCULATIONS_PER_HOUR + 1)
        ]

    assert statuses == [200] * CALCULATIONS_PER_HOUR + [429]


async def test_the_worker_drops_ip_hashes_before_they_are_a_day_old(database: Database) -> None:
    now = datetime(2047, 5, 10, 12, 0, tzinfo=UTC)
    owner = await asyncpg.connect(database.dsn("casero_owner"))
    try:
        for hours_ago, key in ((23, b"old"), (22, b"recent")):
            await owner.execute(
                "INSERT INTO rate_limit_buckets (key_hash, window_start, count) VALUES ($1, $2, 1)",
                key,
                now - timedelta(hours=hours_ago, minutes=1),
            )
        url = database.dsn("casero_worker").replace("postgresql://", "postgresql+asyncpg://", 1)
        engine = create_engine(url)
        try:
            await purge_expired_buckets(engine, FixedClock(now))
        finally:
            await engine.dispose()
        left = await owner.fetch(
            "SELECT key_hash FROM rate_limit_buckets WHERE key_hash = ANY($1)", [b"old", b"recent"]
        )
    finally:
        await owner.close()

    assert [row["key_hash"] for row in left] == [b"recent"]
