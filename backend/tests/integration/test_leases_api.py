from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4, uuid7

import asyncpg
import pytest
from fastapi.testclient import TestClient

from api_client import FixedClock, address_for, api_client
from database import Database

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 27, 15, 0, tzinfo=UTC)
CSRF = "__Host-casero_csrf"


@dataclass(frozen=True)
class Place:
    property_id: str
    units: list[str]
    renter_id: str


def send(client: TestClient, method: str, path: str, body: object = None) -> Any:
    return client.request(method, path, json=body, headers={"X-CSRF-Token": client.cookies[CSRF]})


def register(client: TestClient, email: str) -> None:
    client.get("/api/public/csrf")
    response = client.post(
        "/api/public/registration",
        json={
            "email": email,
            "password": "una clave bien larga",
            "display_name": "Casera",
            "accept_terms_and_privacy": True,
            "consent_sensitive_data": True,
        },
        headers={"X-CSRF-Token": client.cookies[CSRF]},
    )
    assert response.status_code == 201


def set_up(client: TestClient, ownership: str = "sole") -> Place:
    register(client, f"{uuid7()}@example.com")
    house = send(
        client,
        "POST",
        "/api/app/properties",
        {
            "name": "Casa de Surco",
            "ownership": ownership,
            "units": [{"name": "Cuarto 1", "kind": "room"}, {"name": "Cuarto 2", "kind": "room"}],
        },
    ).json()
    renter = send(client, "POST", "/api/app/renters", {"full_name": "Ana Quispe"}).json()
    return Place(house["id"], [unit["id"] for unit in house["units"]], renter["id"])


def lease_body(place: Place, **overrides: object) -> dict[str, Any]:
    body: dict[str, Any] = {
        "id": str(uuid7()),
        "unit_id": place.units[0],
        "renter_id": place.renter_id,
        "monthly_rent_cents": 80_000,
        "due_day": 5,
        "start_date": "2025-06-01",
        "end_date": None,
        "control_from_period": "2026-09",
        "tax_treatment": "standard",
    }
    return {**body, **overrides}


async def owner(database: Database, query: str, *args: object) -> list[asyncpg.Record]:
    connection = await asyncpg.connect(database.dsn("casero_owner"))
    try:
        return await connection.fetch(query, *args)
    finally:
        await connection.close()


def client_for(database: Database, request: pytest.FixtureRequest) -> Any:
    return api_client(
        database, address_for(request.node.name), FixedClock(NOW), registration_mode="open"
    )


async def test_a_lease_starts_with_its_first_rent_and_prior_balances(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with client_for(database, request) as client:
        place = set_up(client)
        body = lease_body(
            place,
            opening_balance_pre_2026_cents=120_000,
            opening_balance_2026_cents=50_050,
        )
        created = send(client, "POST", "/api/app/leases", body)
        listed = client.get("/api/app/leases").json()

    assert created.status_code == 201
    assert created.json() == {
        "id": body["id"],
        "unit_id": place.units[0],
        "renter_id": place.renter_id,
        "monthly_rent_cents": 80_000,
        "due_day": 5,
        "start_date": "2025-06-01",
        "end_date": None,
        "ended_at": None,
        "control_from_period": "2026-09",
        "tax_treatment": "standard",
        "days_to_end": None,
        "ending_soon": False,
    }
    assert listed == [created.json()]
    changes = await owner(
        database,
        "SELECT monthly_rent_cents, effective_period FROM lease_rent_changes"
        " WHERE lease_id = $1::uuid",
        body["id"],
    )
    assert [tuple(row) for row in changes] == [(80_000, "2026-09")]
    charges = await owner(
        database,
        "SELECT kind, amount_cents, pre_2026, period, due_date::text FROM charges"
        " WHERE lease_id = $1::uuid ORDER BY due_date, pre_2026 DESC",
        body["id"],
    )
    assert [tuple(row) for row in charges] == [
        ("opening_balance", 120_000, True, None, "2025-12-31"),
        ("opening_balance", 50_050, False, None, "2026-08-31"),
        ("rent", 80_000, None, "2026-09", "2026-09-05"),
        ("rent", 80_000, None, "2026-10", "2026-10-05"),
    ]


async def test_sending_the_same_lease_again_creates_nothing(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with client_for(database, request) as client:
        place = set_up(client)
        body = lease_body(place, opening_balance_pre_2026_cents=120_000)
        first = send(client, "POST", "/api/app/leases", body)
        again = send(client, "POST", "/api/app/leases", body)
        changed = send(client, "POST", "/api/app/leases", {**body, "due_day": 6})
        other_unit = send(client, "POST", "/api/app/leases", {**body, "unit_id": place.units[1]})

    assert (first.status_code, again.status_code) == (201, 200)
    assert again.json() == first.json()
    assert changed.status_code == 409
    assert other_unit.status_code == 409
    rows = await owner(
        database,
        "SELECT kind, count(*) FROM charges WHERE lease_id = $1::uuid GROUP BY kind ORDER BY kind",
        body["id"],
    )
    assert [tuple(row) for row in rows] == [("opening_balance", 1), ("rent", 2)]


async def test_an_id_taken_in_another_account_is_a_bare_conflict(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with client_for(database, request) as ana, client_for(database, request) as luis:
        ana_place = set_up(ana)
        luis_place = set_up(luis)
        body = lease_body(ana_place)
        send(ana, "POST", "/api/app/leases", body)
        taken = send(luis, "POST", "/api/app/leases", lease_body(luis_place, id=body["id"]))
        foreign_unit = send(luis, "POST", "/api/app/leases", lease_body(ana_place))
        luis_list = luis.get("/api/app/leases").json()

    assert (taken.status_code, taken.json()["detail"]) == (409, "Conflict")
    assert (foreign_unit.status_code, foreign_unit.json()["detail"]) == (404, "unit_not_found")
    assert luis_list == []


async def test_a_unit_holds_one_active_lease_and_must_be_in_use(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with client_for(database, request) as client:
        place = set_up(client)
        no_renter = send(
            client, "POST", "/api/app/leases", lease_body(place, renter_id=str(uuid4()))
        )
        send(client, "POST", "/api/app/leases", lease_body(place))
        occupied = send(client, "POST", "/api/app/leases", lease_body(place))
        send(client, "POST", f"/api/app/units/{place.units[1]}/archive")
        archived = send(
            client, "POST", "/api/app/leases", lease_body(place, unit_id=place.units[1])
        )

    assert (occupied.status_code, occupied.json()["detail"]) == (409, "unit_occupied")
    assert (archived.status_code, archived.json()["detail"]) == (409, "unit_archived")
    assert (no_renter.status_code, no_renter.json()["detail"]) == (404, "renter_not_found")


@pytest.mark.parametrize(
    ("overrides", "detail"),
    [
        ({"control_from_period": "2025-12"}, "control_period_out_of_range"),
        ({"control_from_period": "2026-11"}, "control_period_out_of_range"),
        (
            {"start_date": "2026-12-05", "control_from_period": "2026-10"},
            "control_period_out_of_range",
        ),
        (
            {"control_from_period": "2026-01", "opening_balance_2026_cents": 10_000},
            "balance_2026_without_months",
        ),
        ({"end_date": "2025-05-31"}, "end_before_start"),
        ({"end_date": "2026-08-31"}, "end_before_control"),
        (
            {"start_date": "2026-03-01", "opening_balance_pre_2026_cents": 10_000},
            "balance_pre_2026_without_months",
        ),
        ({"id": str(uuid4())}, None),
        ({"monthly_rent_cents": 0}, None),
        ({"due_day": 32}, None),
    ],
)
async def test_invalid_leases_are_refused(
    database: Database,
    request: pytest.FixtureRequest,
    overrides: dict[str, object],
    detail: str | None,
) -> None:
    with client_for(database, request) as client:
        place = set_up(client)
        response = send(client, "POST", "/api/app/leases", lease_body(place, **overrides))
        listed = client.get("/api/app/leases").json()

    assert response.status_code == 422
    if detail is not None:
        assert response.json()["detail"] == detail
    assert listed == []


async def test_spouses_declaring_halves_get_the_unsupported_treatment(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with client_for(database, request) as client:
        place = set_up(client, ownership="conjugal_split")
        lease = send(client, "POST", "/api/app/leases", lease_body(place)).json()
        flip = send(
            client,
            "PUT",
            f"/api/app/properties/{place.property_id}",
            {"name": "Casa de Surco", "ownership": "sole"},
        )

    assert lease["tax_treatment"] == "unsupported"
    assert (flip.status_code, flip.json()["detail"]) == (409, "active_lease")


async def test_the_free_plan_allows_one_active_lease(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with client_for(database, request) as client:
        place = set_up(client)
        await owner(
            database,
            "UPDATE subscriptions SET ended_at = DATE '2026-10-01'"
            " WHERE account_id = (SELECT account_id FROM units WHERE id = $1::uuid)",
            place.units[0],
        )
        first = send(client, "POST", "/api/app/leases", lease_body(place))
        second = send(client, "POST", "/api/app/leases", lease_body(place, unit_id=place.units[1]))

    assert first.status_code == 201
    assert (second.status_code, second.json()["detail"]) == (409, "plan_limit")


async def test_the_list_warns_15_days_before_the_planned_end(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with client_for(database, request) as client:
        place = set_up(client)
        send(client, "POST", "/api/app/leases", lease_body(place, end_date="2026-11-10"))
        send(
            client,
            "POST",
            "/api/app/leases",
            lease_body(place, unit_id=place.units[1], end_date="2027-03-31"),
        )
        listed = client.get("/api/app/leases").json()

    assert [(lease["days_to_end"], lease["ending_soon"]) for lease in listed] == [
        (14, True),
        (155, False),
    ]


async def test_writes_need_the_csrf_token(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with client_for(database, request) as client:
        place = set_up(client)
        response = client.post("/api/app/leases", json=lease_body(place))

    assert (response.status_code, response.json()["detail"]) == (403, "csrf")


def test_leases_need_a_session(database: Database, request: pytest.FixtureRequest) -> None:
    with api_client(database, address_for(request.node.name)) as client:
        assert client.get("/api/app/leases").status_code == 401
