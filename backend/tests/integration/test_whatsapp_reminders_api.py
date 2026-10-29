import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid7

import asyncpg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncConnection

from api_client import TEST_TENANT_LINK_KEYS, FixedClock, address_for, api_client
from casero.accounts.application.context import AccountContext
from casero.accounts.application.entitlements import GetEntitlements
from casero.accounts.infrastructure.account import SqlPlans, SqlSubscriptions
from casero.shared.infrastructure.audit import SqlAuditLog
from casero.shared.infrastructure.database import create_engine, set_account_context
from casero.tenant_portal.application.links import IssueLink, LinkInUse, Links
from casero.tenant_portal.infrastructure.links import HmacLinkSigner, SqlLinks
from database import Database

pytestmark = pytest.mark.anyio

OCTOBER_27 = datetime(2026, 10, 27, 15, 0, tzinfo=UTC)
CSRF = "__Host-casero_csrf"


def send(client: TestClient, method: str, path: str, body: object = None) -> Any:
    return client.request(method, path, json=body, headers={"X-CSRF-Token": client.cookies[CSRF]})


def start_lease(client: TestClient, phone: str | None = "987654321") -> str:
    client.get("/api/public/csrf")
    registered = send(
        client,
        "POST",
        "/api/public/registration",
        {
            "email": f"{uuid7()}@example.com",
            "password": "una clave bien larga",
            "display_name": "Casera",
            "accept_terms_and_privacy": True,
            "consent_sensitive_data": True,
        },
    )
    assert registered.status_code == 201
    house = send(
        client,
        "POST",
        "/api/app/properties",
        {"name": "Casa", "ownership": "sole", "units": [{"name": "Cuarto", "kind": "room"}]},
    ).json()
    renter = send(
        client, "POST", "/api/app/renters", {"full_name": "Ana Quispe", "phone": phone}
    ).json()
    lease = {
        "id": str(uuid7()),
        "unit_id": house["units"][0]["id"],
        "renter_id": renter["id"],
        "monthly_rent_cents": 80_000,
        "due_day": 30,
        "start_date": "2026-03-01",
        "control_from_period": "2026-10",
        "tax_treatment": "standard",
    }
    assert send(client, "POST", "/api/app/leases", lease).status_code == 201
    return str(lease["id"])


def remind(client: TestClient, lease_id: str) -> Any:
    return send(client, "POST", f"/api/app/leases/{lease_id}/whatsapp-reminders")


def text_of(url: str) -> str:
    return parse_qs(urlsplit(url).query)["text"][0]


def client_for(database: Database, request: pytest.FixtureRequest, clock: FixedClock) -> Any:
    return api_client(database, address_for(request.node.name), clock, registration_mode="open")


async def reminder_rows(database: Database, lease_id: str) -> list[tuple[str, str]]:
    owner = await asyncpg.connect(database.dsn("casero_owner"))
    try:
        rows = await owner.fetch(
            "SELECT g.kind, g.channel FROM reminder_logs g JOIN charges c ON c.id = g.charge_id"
            " WHERE c.lease_id = $1 ORDER BY g.created_at",
            lease_id,
        )
    finally:
        await owner.close()
    return [(row["kind"], row["channel"]) for row in rows]


async def test_the_message_follows_the_rents_status_and_carries_the_tenants_link(
    database: Database, request: pytest.FixtureRequest
) -> None:
    clock = FixedClock(OCTOBER_27)
    with client_for(database, request, clock) as client:
        lease_id = start_lease(client)
        soon = remind(client, lease_id)
        clock.advance(timedelta(days=3))
        today = remind(client, lease_id)
        clock.advance(timedelta(days=1))
        late = remind(client, lease_id)
        link = client.get(f"/api/app/leases/{lease_id}/tenant-link").json()["link"]["url"]

    assert [r.status_code for r in (soon, today, late)] == [201, 201, 201]
    assert [r.json()["kind"] for r in (soon, today, late)] == ["friendly", "due_today", "overdue"]
    assert soon.json()["message"] == (
        "Hola Ana Quispe, te recuerdo que el 30/10/2026 vence el alquiler de octubre de 2026"
        f" por S/ 800.00. Puedes ver tu detalle aquí: {link}. ¡Gracias!"
    )
    assert today.json()["message"] == (
        "Hola Ana Quispe, hoy vence el alquiler de octubre de 2026 por S/ 800.00."
        f" Tu detalle está aquí: {link}."
    )
    assert late.json()["message"] == (
        "Hola Ana Quispe, el alquiler de octubre de 2026 por S/ 800.00 está pendiente desde"
        f" el 30/10/2026. ¿Me confirmas cuándo podrías pagarlo? Tu detalle: {link}."
    )
    assert late.json()["url"].startswith("https://wa.me/51987654321?text=")
    assert text_of(late.json()["url"]) == late.json()["message"]
    assert await reminder_rows(database, lease_id) == [("rent", "whatsapp_link")] * 3


async def test_it_reminds_what_is_left_and_nothing_once_paid(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with client_for(database, request, FixedClock(OCTOBER_27)) as client:
        lease_id = start_lease(client, phone=None)
        pay = {"amount_cents": 50_000, "received_on": "2026-10-26", "method": "yape"}
        send(client, "POST", f"/api/app/leases/{lease_id}/payments", {"id": str(uuid7()), **pay})
        partial = remind(client, lease_id)
        send(client, "POST", f"/api/app/leases/{lease_id}/payments", {"id": str(uuid7()), **pay})
        paid = remind(client, lease_id)

    assert "por S/ 300.00" in partial.json()["message"]
    assert partial.json()["url"].startswith("https://wa.me/?text=")
    assert (paid.status_code, paid.json()["detail"]) == (409, "nothing_due")
    assert await reminder_rows(database, lease_id) == [("rent", "whatsapp_link")]


async def test_a_message_without_the_link_variable_issues_no_link(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with client_for(database, request, FixedClock(OCTOBER_27)) as client:
        lease_id = start_lease(client)
        body = {"body": "Hola {inquilino}, el {fecha} vence {monto}."}
        send(client, "PUT", "/api/app/message-templates/friendly", body)
        reminder = remind(client, lease_id)
        link = client.get(f"/api/app/leases/{lease_id}/tenant-link").json()["link"]

    assert reminder.json()["message"] == "Hola Ana Quispe, el 30/10/2026 vence S/ 800.00."
    assert link is None


async def test_a_lease_without_whatsapp_or_from_another_account_gets_none(
    database: Database, request: pytest.FixtureRequest
) -> None:
    clock = FixedClock(OCTOBER_27)
    with client_for(database, request, clock) as ana, client_for(database, request, clock) as luis:
        lease_id = start_lease(ana)
        start_lease(luis)
        from_luis = remind(luis, lease_id)
        unknown = remind(ana, str(uuid7()))
        owner = await asyncpg.connect(database.dsn("casero_owner"))
        try:
            await owner.execute("UPDATE leases SET tools_enabled = false WHERE id = $1", lease_id)
        finally:
            await owner.close()
        without_tools = remind(ana, lease_id)
        no_csrf = ana.post(f"/api/app/leases/{lease_id}/whatsapp-reminders")

    assert (from_luis.status_code, from_luis.json()["detail"]) == (404, "lease_not_found")
    assert unknown.status_code == 404
    assert (without_tools.status_code, without_tools.json()["detail"]) == (
        403,
        "whatsapp_unavailable",
    )
    assert no_csrf.status_code == 403
    assert await reminder_rows(database, lease_id) == []


async def test_the_panel_knows_how_many_lima_days_ago_each_lease_was_reminded(
    database: Database, request: pytest.FixtureRequest
) -> None:
    clock = FixedClock(datetime(2026, 10, 29, 3, 0, tzinfo=UTC))
    with client_for(database, request, clock) as ana, client_for(database, request, clock) as luis:
        lease_id = start_lease(ana)
        start_lease(luis)
        before = ana.get("/api/app/whatsapp-reminders").json()
        remind(ana, lease_id)
        same_night = ana.get("/api/app/whatsapp-reminders").json()
        clock.advance(timedelta(days=2))
        later = ana.get("/api/app/whatsapp-reminders").json()
        seen_by_luis = luis.get("/api/app/whatsapp-reminders").json()

    assert before == []
    assert same_night == [{"lease_id": lease_id, "sent_on": "2026-10-28", "days_ago": 0}]
    assert later == [{"lease_id": lease_id, "sent_on": "2026-10-28", "days_ago": 2}]
    assert seen_by_luis == []


async def context_of(database: Database, lease_id: str) -> AccountContext:
    owner = await asyncpg.connect(database.dsn("casero_owner"))
    try:
        row = await owner.fetchrow(
            "SELECT l.account_id, m.user_id FROM leases l"
            " JOIN account_members m USING (account_id) WHERE l.id = $1",
            UUID(lease_id),
        )
        links = await owner.fetchval(
            "SELECT count(*) FROM tenant_links WHERE lease_id = $1", UUID(lease_id)
        )
    finally:
        await owner.close()
    assert row is not None
    assert links == 0
    return AccountContext(row["account_id"], row["user_id"])


@asynccontextmanager
async def two_transactions(
    database: Database, context: AccountContext
) -> AsyncIterator[tuple[AsyncConnection, AsyncConnection]]:
    engine = create_engine(
        database.dsn("casero_app").replace("postgresql://", "postgresql+asyncpg://", 1)
    )
    try:
        async with engine.connect() as first, engine.connect() as second:
            for connection in (first, second):
                await connection.begin()
                await set_account_context(connection, context.account_id)
            yield first, second
    finally:
        await engine.dispose()


def link_in_use(connection: AsyncConnection) -> LinkInUse:
    clock = FixedClock(OCTOBER_27)
    links = Links(SqlLinks(connection), HmacLinkSigner(TEST_TENANT_LINK_KEYS), "https://x.test")
    entitlements = GetEntitlements(SqlSubscriptions(connection), SqlPlans(connection), clock)
    return LinkInUse(links, IssueLink(links, entitlements, SqlAuditLog(connection), clock))


async def test_two_messages_prepared_at_once_share_one_link(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with client_for(database, request, FixedClock(OCTOBER_27)) as client:
        lease_id = start_lease(client)
    context = await context_of(database, lease_id)

    async with two_transactions(database, context) as (first, second):
        url = await link_in_use(first).url_for(context, UUID(lease_id))
        other = asyncio.create_task(link_in_use(second).url_for(context, UUID(lease_id)))
        await asyncio.sleep(0.3)
        waited_for_the_lease = not other.done()
        await first.commit()
        same = await other
        await second.commit()

    assert url is not None
    assert waited_for_the_lease
    assert same == url
