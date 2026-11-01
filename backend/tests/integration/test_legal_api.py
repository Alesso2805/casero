from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid7

import asyncpg
import pytest

from api_client import FixedClock
from database import Database
from tax_flows import client_for, register, send

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 27, 15, 0, tzinfo=UTC)
LEGAL = "/api/app/legal"
ACCEPTANCES = "/api/app/legal/acceptances"
WITHDRAWAL = "/api/app/legal/consent-withdrawal"
# Far from every other test's clock, because legal_documents is shared by the whole database.
BEFORE_NEW_TERMS = datetime(2031, 1, 10, 15, 0, tzinfo=UTC)
NEW_TERMS_ON = date(2031, 1, 15)


async def owner_fetch(database: Database, query: str, *args: object) -> list[asyncpg.Record]:
    owner = await asyncpg.connect(database.dsn("casero_owner"))
    try:
        return await owner.fetch(query, *args)
    finally:
        await owner.close()


async def publish_new_terms(database: Database) -> UUID:
    document_id = uuid7()
    await owner_fetch(
        database,
        "INSERT INTO legal_documents (id, kind, version, published_at, url)"
        " VALUES ($1, 'terms', '0.2', $2, '/legal/terminos/0.2')",
        document_id,
        NEW_TERMS_ON,
    )
    return document_id


async def document_id_of(database: Database, kind: str) -> UUID:
    [row] = await owner_fetch(
        database, "SELECT id FROM legal_documents WHERE kind = $1 AND version = '0.1'", kind
    )
    document_id: UUID = row["id"]
    return document_id


def pending_kinds(status: Any) -> list[tuple[str, str]]:
    return [(document["kind"], document["version"]) for document in status["pending"]]


async def test_a_new_version_blocks_the_account_until_it_is_accepted(
    database: Database, request: pytest.FixtureRequest
) -> None:
    clock = FixedClock(BEFORE_NEW_TERMS)
    old_terms = await document_id_of(database, "terms")
    with client_for(database, request, clock) as client:
        register(client)
        before = client.get("/api/app/account")
        new_terms = await publish_new_terms(database)
        clock.advance(timedelta(days=6))
        blocked = client.get("/api/app/account")
        status = client.get(LEGAL)
        outdated = send(client, "POST", ACCEPTANCES, {"document_ids": [str(old_terms)]})
        accepted = send(client, "POST", ACCEPTANCES, {"document_ids": [str(new_terms)]})
        again = send(client, "POST", ACCEPTANCES, {"document_ids": [str(new_terms)]})
        after = client.get("/api/app/account")

    assert before.status_code == 200
    assert (blocked.status_code, blocked.json()["detail"]) == (403, "legal_acceptance_required")
    assert status.json() == {
        "pending": [
            {
                "id": str(new_terms),
                "kind": "terms",
                "version": "0.2",
                "url": "/legal/terminos/0.2",
            }
        ],
        "consent_withdrawn": False,
    }
    assert (outdated.status_code, outdated.json()["detail"]) == (422, "document_not_current")
    assert (accepted.status_code, accepted.json()["pending"]) == (200, [])
    assert (again.status_code, again.json()["pending"]) == (200, [])
    assert after.status_code == 200
    rows = await owner_fetch(
        database, "SELECT ip_hash FROM legal_acceptances WHERE document_id = $1", new_terms
    )
    assert [len(row["ip_hash"]) for row in rows] == [32]


async def test_withdrawing_the_consent_blocks_all_but_the_rights_of_that_account(
    database: Database, request: pytest.FixtureRequest
) -> None:
    clock = FixedClock(NOW)
    consent = await document_id_of(database, "sensitive_consent")
    with client_for(database, request, clock) as ana, client_for(database, request, clock) as luis:
        ana_email = f"{uuid7()}@example.com"
        register(ana, ana_email)
        register(luis)
        clock.advance(timedelta(minutes=1))
        withdrawn = send(ana, "POST", WITHDRAWAL)
        again = send(ana, "POST", WITHDRAWAL)
        account = ana.get("/api/app/account")
        properties = ana.get("/api/app/properties")
        status = ana.get(LEGAL)
        other_account = luis.get("/api/app/account")
        clock.advance(timedelta(minutes=1))
        given = send(ana, "POST", ACCEPTANCES, {"document_ids": [str(consent)]})
        back = ana.get("/api/app/account")

    assert (withdrawn.status_code, withdrawn.json()["consent_withdrawn"]) == (200, True)
    assert pending_kinds(withdrawn.json()) == [("sensitive_consent", "0.1")]
    assert (again.status_code, again.json()) == (200, withdrawn.json())
    assert (account.status_code, account.json()["detail"]) == (403, "consent_withdrawn")
    assert (properties.status_code, properties.json()["detail"]) == (403, "consent_withdrawn")
    assert status.json() == withdrawn.json()
    assert other_account.status_code == 200
    assert (given.json()["consent_withdrawn"], given.json()["pending"]) == (False, [])
    assert back.status_code == 200
    rows = await owner_fetch(
        database,
        "SELECT w.document_id FROM legal_withdrawals w JOIN users u ON u.id = w.user_id"
        " WHERE u.email = $1",
        ana_email,
    )
    assert [row["document_id"] for row in rows] == [consent]


async def test_the_legal_routes_need_a_session_and_a_real_document(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with client_for(database, request, FixedClock(NOW)) as client:
        anonymous = client.get(LEGAL)
        register(client)
        empty = send(client, "POST", ACCEPTANCES, {"document_ids": []})
        unknown = send(client, "POST", ACCEPTANCES, {"document_ids": [str(uuid7())]})

    assert anonymous.status_code == 401
    assert empty.status_code == 422
    assert (unknown.status_code, unknown.json()["detail"]) == (422, "document_not_current")
