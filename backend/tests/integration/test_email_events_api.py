import json
from uuid import uuid7

import asyncpg
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

import sns_signing
from api_client import TEST_EMAIL_HASH_KEY, TEST_TOPIC_ARN, address_for, api_client
from casero.identity.infrastructure.email_suppressions import SuppressionLookup, email_hash
from casero.shared.infrastructure.database import create_engine
from database import Database

pytestmark = pytest.mark.anyio

EVENTS = "/api/public/email-events"


def post(database: Database, name: str, body: bytes) -> int:
    sns = sns_signing.FakeSns()
    with api_client(database, address_for(name), sns_verifier=sns.verifier()) as client:
        response = client.post(
            EVENTS, content=body, headers={"Content-Type": "text/plain; charset=UTF-8"}
        )
    return response.status_code


async def worker_engine(database: Database) -> AsyncEngine:
    url = database.dsn("casero_worker").replace("postgresql://", "postgresql+asyncpg://", 1)
    return create_engine(url)


async def test_a_signed_bounce_suppresses_the_address_for_every_email(
    database: Database, request: pytest.FixtureRequest
) -> None:
    address = f"{uuid7()}@Example.com"
    message = sns_signing.notification(TEST_TOPIC_ARN, sns_signing.permanent_bounce(address))

    assert post(database, request.node.name, json.dumps(message).encode()) == 200

    owner = await asyncpg.connect(database.dsn("casero_owner"))
    try:
        row = await owner.fetchrow(
            "SELECT email_kind, reason FROM email_suppressions WHERE email_hash = $1",
            email_hash(TEST_EMAIL_HASH_KEY, address.lower()),
        )
    finally:
        await owner.close()
    assert row is not None
    assert tuple(row) == (None, "bounce")
    engine = await worker_engine(database)
    try:
        assert await SuppressionLookup(engine, TEST_EMAIL_HASH_KEY).blocks(f"  {address.upper()} ")
        assert not await SuppressionLookup(engine, TEST_EMAIL_HASH_KEY).blocks("otro@example.com")
    finally:
        await engine.dispose()


async def test_a_repeated_notification_is_harmless(
    database: Database, request: pytest.FixtureRequest
) -> None:
    message = sns_signing.notification(
        TEST_TOPIC_ARN, sns_signing.permanent_bounce(f"{uuid7()}@example.com")
    )
    body = json.dumps(message).encode()

    assert [post(database, request.node.name, body) for _ in range(2)] == [200, 200]


@pytest.mark.parametrize(
    ("body", "status"),
    [
        (b"not json", 400),
        (b"[]", 400),
        (
            json.dumps(
                sns_signing.notification(
                    "arn:aws:sns:us-east-1:000000000000:other",
                    sns_signing.permanent_bounce("a@example.com"),
                )
            ).encode(),
            403,
        ),
        (
            json.dumps(
                {
                    **sns_signing.notification(
                        TEST_TOPIC_ARN, sns_signing.permanent_bounce("a@example.com")
                    ),
                    "Message": json.dumps(sns_signing.permanent_bounce("b@example.com")),
                }
            ).encode(),
            403,
        ),
    ],
)
async def test_foreign_or_forged_messages_are_refused(
    database: Database, request: pytest.FixtureRequest, body: bytes, status: int
) -> None:
    assert post(database, request.node.name, body) == status
