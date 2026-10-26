from datetime import UTC, datetime
from uuid import UUID, uuid7

import asyncpg
import pytest

from api_client import TEST_EMAIL_HASH_KEY, TEST_UNSUBSCRIBE_KEY, address_for, api_client
from casero.identity.infrastructure.email_suppressions import SqlSuppressionStore
from casero.identity.infrastructure.unsubscribe import HmacUnsubscribeTokens
from casero.shared.infrastructure.database import create_engine
from database import Database

pytestmark = pytest.mark.anyio

TOKENS = HmacUnsubscribeTokens(TEST_UNSUBSCRIBE_KEY)
NOW = datetime(2026, 10, 26, 15, 0, tzinfo=UTC)


async def a_user(database: Database) -> tuple[UUID, str]:
    user_id, email = uuid7(), f"{uuid7()}@example.com"
    owner = await asyncpg.connect(database.dsn("casero_owner"))
    try:
        await owner.execute(
            "INSERT INTO users (id, email, password_hash, created_at) VALUES ($1, $2, 'x', $3)",
            user_id,
            email,
            NOW,
        )
    finally:
        await owner.close()
    return user_id, email


def unsubscribe(database: Database, name: str, query: dict[str, str]) -> int:
    with api_client(database, address_for(name)) as client:
        response = client.post(
            "/api/public/unsubscribe",
            params=query,
            content=b"List-Unsubscribe=One-Click",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    return response.status_code


async def blocked(database: Database, email: str) -> dict[str | None, bool]:
    url = database.dsn("casero_worker").replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_engine(url)
    try:
        async with engine.connect() as connection:
            store = SqlSuppressionStore(connection, TEST_EMAIL_HASH_KEY)
            return {
                kind: await store.blocks(email, kind)
                for kind in (None, "daily_digest", "tax_reminders")
            }
    finally:
        await engine.dispose()


async def test_one_click_stops_only_that_kind_of_email(
    database: Database, request: pytest.FixtureRequest
) -> None:
    user_id, email = await a_user(database)
    query = {"u": str(user_id), "k": "daily_digest", "t": TOKENS.token(user_id, "daily_digest")}

    assert unsubscribe(database, request.node.name, query) == 204
    assert unsubscribe(database, request.node.name, query) == 204
    assert await blocked(database, email) == {
        None: False,
        "daily_digest": True,
        "tax_reminders": False,
    }


async def test_a_link_for_another_kind_or_user_is_refused(
    database: Database, request: pytest.FixtureRequest
) -> None:
    user_id, email = await a_user(database)
    other = uuid7()

    assert (
        unsubscribe(
            database,
            request.node.name,
            {"u": str(user_id), "k": "tax_reminders", "t": TOKENS.token(user_id, "daily_digest")},
        )
        == 403
    )
    assert (
        unsubscribe(
            database,
            request.node.name,
            {"u": str(user_id), "k": "daily_digest", "t": TOKENS.token(other, "daily_digest")},
        )
        == 403
    )
    assert (
        unsubscribe(database, request.node.name, {"u": "x", "k": "daily_digest", "t": "x"}) == 422
    )
    assert await blocked(database, email) == {
        None: False,
        "daily_digest": False,
        "tax_reminders": False,
    }
