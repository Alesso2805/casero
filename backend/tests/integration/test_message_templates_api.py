from datetime import UTC, datetime
from typing import Any
from uuid import uuid7

import asyncpg
import pytest
from fastapi.testclient import TestClient

from api_client import FixedClock, address_for, api_client
from casero.reminders.domain.messages import DEFAULT_BODIES
from database import Database

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 29, 15, 0, tzinfo=UTC)
CSRF = "__Host-casero_csrf"
FIRM = "Hola {inquilino}, el alquiler de {periodo} ({monto}) sigue pendiente. {enlace}"


def send(client: TestClient, method: str, path: str, body: object = None) -> Any:
    return client.request(method, path, json=body, headers={"X-CSRF-Token": client.cookies[CSRF]})


def register(client: TestClient, email: str) -> None:
    client.get("/api/public/csrf")
    registered = send(
        client,
        "POST",
        "/api/public/registration",
        {
            "email": email,
            "password": "una clave bien larga",
            "display_name": "Casera",
            "accept_terms_and_privacy": True,
            "consent_sensitive_data": True,
        },
    )
    assert registered.status_code == 201


def client_for(database: Database, request: pytest.FixtureRequest) -> Any:
    return api_client(
        database, address_for(request.node.name), FixedClock(NOW), registration_mode="open"
    )


async def audit_actions(database: Database, email: str) -> list[tuple[str, list[str]]]:
    owner = await asyncpg.connect(database.dsn("casero_owner"))
    try:
        rows = await owner.fetch(
            "SELECT a.action, a.changed_fields FROM audit_log a"
            " JOIN account_members m ON m.account_id = a.account_id"
            " JOIN users u ON u.id = m.user_id WHERE u.email = $1"
            " AND a.entity = 'message_templates' ORDER BY a.at, a.id",
            email,
        )
    finally:
        await owner.close()
    return [(row["action"], list(row["changed_fields"])) for row in rows]


async def test_each_account_starts_with_specs_messages_and_edits_its_own(
    database: Database, request: pytest.FixtureRequest
) -> None:
    email = f"{uuid7()}@example.com"
    with client_for(database, request) as ana, client_for(database, request) as luis:
        register(ana, email)
        register(luis, f"{uuid7()}@example.com")
        defaults = ana.get("/api/app/message-templates").json()
        saved = send(ana, "PUT", "/api/app/message-templates/overdue", {"body": f"  {FIRM} "})
        after = ana.get("/api/app/message-templates").json()
        restored = send(
            ana, "PUT", "/api/app/message-templates/overdue", {"body": DEFAULT_BODIES["overdue"]}
        )
        seen_by_luis = luis.get("/api/app/message-templates").json()

    assert defaults == [
        {"kind": kind, "body": body, "default_body": body} for kind, body in DEFAULT_BODIES.items()
    ]
    assert saved.status_code == 200
    assert saved.json() == {
        "kind": "overdue",
        "body": FIRM,
        "default_body": DEFAULT_BODIES["overdue"],
    }
    assert [t["body"] for t in after] == [
        DEFAULT_BODIES["friendly"],
        DEFAULT_BODIES["due_today"],
        FIRM,
    ]
    assert restored.json()["body"] == DEFAULT_BODIES["overdue"]
    assert seen_by_luis == defaults
    assert await audit_actions(database, email) == [
        ("message_template.updated", ["overdue"]),
        ("message_template.updated", ["overdue"]),
    ]


@pytest.mark.parametrize(
    ("kind", "body", "detail"),
    [
        ("friendly", {"body": "Hola {nombre}, paga {monto}"}, "unknown_variable"),
        ("friendly", {"body": "   "}, None),
        ("friendly", {"body": "x" * 1001}, None),
        ("reminder", {"body": "Hola"}, None),
    ],
)
async def test_a_message_needs_text_a_known_kind_and_only_known_variables(
    database: Database,
    request: pytest.FixtureRequest,
    kind: str,
    body: dict[str, str],
    detail: str | None,
) -> None:
    with client_for(database, request) as client:
        register(client, f"{uuid7()}@example.com")
        response = send(client, "PUT", f"/api/app/message-templates/{kind}", body)
        templates = client.get("/api/app/message-templates").json()

    assert response.status_code == 422
    if detail:
        assert response.json()["detail"] == detail
    assert [t["body"] for t in templates] == list(DEFAULT_BODIES.values())


async def test_saving_a_message_needs_the_csrf_token(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with client_for(database, request) as client:
        register(client, f"{uuid7()}@example.com")
        response = client.put("/api/app/message-templates/friendly", json={"body": "Hola"})

    assert response.status_code == 403
