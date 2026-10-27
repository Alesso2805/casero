from datetime import UTC, datetime
from typing import Any
from uuid import uuid7

import asyncpg
import pytest
from fastapi.testclient import TestClient

from api_client import FixedClock, address_for, api_client
from database import Database

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 27, 15, 0, tzinfo=UTC)
CSRF = "__Host-casero_csrf"
HOUSE: dict[str, Any] = {
    "name": "Casa de Surco",
    "address_line": "Av. Siempre Viva 123",
    "district": "Surco",
    "ownership": "sole",
    "units": [{"name": "Cuarto 1", "kind": "room"}, {"name": "Cochera", "kind": "parking"}],
}


def register(client: TestClient, email: str) -> None:
    client.get("/api/public/csrf")
    response = client.post(
        "/api/public/registration",
        json={
            "email": email,
            "password": "una clave bien larga",
            "display_name": "Ana",
            "accept_terms_and_privacy": True,
            "consent_sensitive_data": True,
        },
        headers={"X-CSRF-Token": client.cookies[CSRF]},
    )
    assert response.status_code == 201


def send(client: TestClient, method: str, path: str, body: object = None) -> Any:
    return client.request(method, path, json=body, headers={"X-CSRF-Token": client.cookies[CSRF]})


def new_house(client: TestClient, **overrides: object) -> Any:
    response = send(client, "POST", "/api/app/properties", {**HOUSE, **overrides})
    assert response.status_code == 201, response.text
    return response.json()


async def owner_execute(database: Database, query: str, *args: object) -> list[asyncpg.Record]:
    owner = await asyncpg.connect(database.dsn("casero_owner"))
    try:
        return await owner.fetch(query, *args)
    finally:
        await owner.close()


async def audit_actions(database: Database, email: str) -> list[tuple[str, str, list[str]]]:
    rows = await owner_execute(
        database,
        "SELECT a.action, a.entity, a.changed_fields FROM audit_log a"
        " JOIN users u ON u.id = a.actor_user_id WHERE u.email = $1 ORDER BY a.id",
        email,
    )
    return [(row["action"], row["entity"], list(row["changed_fields"])) for row in rows]


async def test_the_landlord_registers_and_edits_properties_and_units(
    database: Database, request: pytest.FixtureRequest
) -> None:
    email = f"{uuid7()}@example.com"
    with api_client(
        database, address_for(request.node.name), FixedClock(NOW), registration_mode="open"
    ) as client:
        register(client, email)
        house = new_house(client)
        edited = send(
            client,
            "PUT",
            f"/api/app/properties/{house['id']}",
            {**HOUSE, "autovaluo_cents": 25_000_000, "rented_share_pct": 40},
        )
        added = send(
            client,
            "POST",
            f"/api/app/properties/{house['id']}/units",
            {"name": "Minidepa", "kind": "mini_apartment"},
        )
        renamed = send(
            client,
            "PUT",
            f"/api/app/units/{house['units'][0]['id']}",
            {"name": "Cuarto grande", "kind": "room"},
        )
        listed = client.get("/api/app/properties").json()

    assert (edited.status_code, added.status_code, renamed.status_code) == (200, 201, 200)
    assert listed == [
        {
            "id": house["id"],
            "name": "Casa de Surco",
            "address_line": "Av. Siempre Viva 123",
            "district": "Surco",
            "ownership": "sole",
            "autovaluo_cents": 25_000_000,
            "rented_share_pct": 40,
            "archived": False,
            "units": [
                {**house["units"][0], "name": "Cuarto grande"},
                house["units"][1],
                added.json(),
            ],
        }
    ]
    assert await audit_actions(database, email) == [
        (
            "property.created",
            "properties",
            [
                "name",
                "address_line",
                "district",
                "ownership",
                "autovaluo_cents",
                "rented_share_pct",
            ],
        ),
        ("unit.created", "units", ["name", "kind"]),
        ("unit.created", "units", ["name", "kind"]),
        ("property.updated", "properties", ["autovaluo_cents", "rented_share_pct"]),
        ("unit.created", "units", ["name", "kind"]),
        ("unit.updated", "units", ["name"]),
    ]


async def test_the_declarant_type_locks_once_the_account_has_a_property(
    database: Database, request: pytest.FixtureRequest
) -> None:
    profile = {"display_name": "Ana", "ruc": None, "daily_digest": False}
    with api_client(
        database, address_for(request.node.name), FixedClock(NOW), registration_mode="open"
    ) as client:
        register(client, f"{uuid7()}@example.com")
        before = client.get("/api/app/account/profile").json()
        new_house(client)
        locked = send(
            client, "PUT", "/api/app/account/profile", {**profile, "taxpayer_kind": "estate"}
        )
        renamed = send(
            client,
            "PUT",
            "/api/app/account/profile",
            {**profile, "display_name": "Ana Q.", "taxpayer_kind": "person"},
        )

    assert before["declarant_locked"] is False
    assert (locked.status_code, locked.json()["detail"]) == (409, "declarant_locked")
    assert renamed.status_code == 200
    assert renamed.json()["declarant_locked"] is True


@pytest.mark.parametrize(
    ("overrides", "detail"),
    [
        ({"ownership": "estate"}, "ownership_mismatch"),
        ({"ownership": "conjugal_option"}, None),
        ({"units": []}, None),
        ({"rented_share_pct": 0}, None),
        ({"autovaluo_cents": 0}, None),
        ({"name": "  "}, None),
        ({"units": [{"name": "Cuarto", "kind": "garage"}]}, None),
    ],
)
async def test_invalid_properties_are_refused(
    database: Database,
    request: pytest.FixtureRequest,
    overrides: dict[str, object],
    detail: str | None,
) -> None:
    with api_client(
        database, address_for(request.node.name), FixedClock(NOW), registration_mode="open"
    ) as client:
        register(client, f"{uuid7()}@example.com")
        response = send(client, "POST", "/api/app/properties", {**HOUSE, **overrides})
        listed = client.get("/api/app/properties").json()

    assert response.status_code == 422
    if detail is not None:
        assert response.json()["detail"] == detail
    assert listed == []


async def test_the_conjugal_option_needs_the_landlords_confirmation(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with api_client(
        database, address_for(request.node.name), FixedClock(NOW), registration_mode="open"
    ) as client:
        register(client, f"{uuid7()}@example.com")
        house = new_house(client, ownership="conjugal_option", conjugal_option_confirmed=True)

    assert house["ownership"] == "conjugal_option"


async def test_an_estate_account_registers_estate_properties_only(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with api_client(
        database, address_for(request.node.name), FixedClock(NOW), registration_mode="open"
    ) as client:
        register(client, f"{uuid7()}@example.com")
        send(
            client,
            "PUT",
            "/api/app/account/profile",
            {
                "display_name": "Sucesión",
                "taxpayer_kind": "estate",
                "ruc": None,
                "daily_digest": False,
            },
        )
        sole = send(client, "POST", "/api/app/properties", HOUSE)
        estate = new_house(client, ownership="estate")
        to_sole = send(
            client, "PUT", f"/api/app/properties/{estate['id']}", {**HOUSE, "ownership": "sole"}
        )

    assert (sole.status_code, sole.json()["detail"]) == (422, "ownership_mismatch")
    assert (to_sole.status_code, to_sole.json()["detail"]) == (422, "ownership_mismatch")


async def test_each_landlord_sees_and_edits_only_their_own_properties(
    database: Database, request: pytest.FixtureRequest
) -> None:
    clock = FixedClock(NOW)
    with (
        api_client(
            database, address_for(request.node.name), clock, registration_mode="open"
        ) as ana,
        api_client(
            database, address_for(request.node.name), clock, registration_mode="open"
        ) as luis,
    ):
        register(ana, f"{uuid7()}@example.com")
        register(luis, f"{uuid7()}@example.com")
        house = new_house(ana)
        unit_id = house["units"][0]["id"]
        attempts = [
            send(luis, "PUT", f"/api/app/properties/{house['id']}", HOUSE),
            send(
                luis,
                "POST",
                f"/api/app/properties/{house['id']}/units",
                {"name": "Intruso", "kind": "room"},
            ),
            send(luis, "PUT", f"/api/app/units/{unit_id}", {"name": "Intruso", "kind": "room"}),
        ]
        luis_list = luis.get("/api/app/properties").json()
        ana_list = ana.get("/api/app/properties").json()

    assert [response.status_code for response in attempts] == [404] * 3
    assert luis_list == []
    assert ana_list == [house]


async def test_writes_need_the_csrf_token(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with api_client(
        database, address_for(request.node.name), FixedClock(NOW), registration_mode="open"
    ) as client:
        register(client, f"{uuid7()}@example.com")
        response = client.post("/api/app/properties", json=HOUSE)

    assert (response.status_code, response.json()["detail"]) == (403, "csrf")


def test_properties_need_a_session(database: Database, request: pytest.FixtureRequest) -> None:
    with api_client(database, address_for(request.node.name)) as client:
        assert client.get("/api/app/properties").status_code == 401
