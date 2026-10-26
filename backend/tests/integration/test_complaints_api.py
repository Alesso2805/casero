from datetime import UTC, date, datetime

import asyncpg
import pytest

from api_client import FixedClock, address_for, api_client
from casero.admin.domain.complaints import RESPONSE_BUSINESS_DAYS, add_business_days
from casero.api import COMPLAINTS_PER_HOUR
from database import Database

pytestmark = pytest.mark.anyio


def sheet(**changes: object) -> dict[str, object]:
    body: dict[str, object] = {
        "full_name": "Ana Quispe Mamani",
        "document_type": "dni",
        "document_number": "12345678",
        "email": "ana@example.com",
        "item_kind": "service",
        "kind": "claim",
        "detail": "Me cobraron dos veces la suscripción.",
        "response_channel": "email",
    }
    body.update(changes)
    return body


async def stored(database: Database, number: str) -> asyncpg.Record:
    owner = await asyncpg.connect(database.dsn("casero_owner"))
    try:
        row = await owner.fetchrow("SELECT * FROM complaints WHERE number = $1", number)
        assert row is not None
        return row
    finally:
        await owner.close()


async def test_a_claim_gets_the_next_number_and_its_deadline(
    database: Database, request: pytest.FixtureRequest
) -> None:
    now = datetime(2041, 3, 4, 15, 0, tzinfo=UTC)
    full = sheet(
        document_number="1234 5678",
        address="Av. Siempre Viva 742, Lima",
        phone="+51 999 888 777",
        guardian={"full_name": "Rosa Mamani", "phone": "+51 999 111 222"},
        claimed_amount_cents=1900,
        item_description="Plan Casero mensual",
        request="Que me devuelvan el cobro repetido.",
    )

    with api_client(database, address_for(request.node.name), FixedClock(now)) as client:
        first = client.post("/api/public/complaints", json=full)
        second = client.post("/api/public/complaints", json=sheet(kind="complaint"))

    assert first.status_code == 201
    assert first.json() == {
        "number": "000000001-2041",
        "filed_at": "2041-03-04T15:00:00Z",
        "due_on": add_business_days(
            date(2041, 3, 4), RESPONSE_BUSINESS_DAYS, frozenset()
        ).isoformat(),
    }
    assert second.json()["number"] == "000000002-2041"
    row = await stored(database, "000000001-2041")
    assert row["document_number"] == "12345678"
    assert row["guardian_name"] == "Rosa Mamani"
    assert row["guardian_address"] is None
    assert row["claimed_amount_cents"] == 1900
    assert row["created_at"] == now
    assert row["response"] is None


async def test_national_holidays_move_the_deadline(
    database: Database, request: pytest.FixtureRequest
) -> None:
    filed_on = date(2042, 3, 3)
    holiday = date(2042, 3, 6)
    owner = await asyncpg.connect(database.dsn("casero_owner"))
    try:
        await owner.execute(
            "INSERT INTO holidays (date, name) VALUES ($1, 'Feriado de prueba')", holiday
        )
    finally:
        await owner.close()
    now = datetime(2042, 3, 3, 15, 0, tzinfo=UTC)

    with api_client(database, address_for(request.node.name), FixedClock(now)) as client:
        response = client.post("/api/public/complaints", json=sheet())

    expected = add_business_days(filed_on, RESPONSE_BUSINESS_DAYS, frozenset({holiday}))
    assert expected != add_business_days(filed_on, RESPONSE_BUSINESS_DAYS, frozenset())
    assert response.json()["due_on"] == expected.isoformat()


async def test_a_letter_answer_needs_only_an_address(
    database: Database, request: pytest.FixtureRequest
) -> None:
    body = sheet(email=None, address="Jr. Los Pinos 123, Arequipa", response_channel="letter")

    with api_client(database, address_for(request.node.name)) as client:
        response = client.post("/api/public/complaints", json=body)

    assert response.status_code == 201
    row = await stored(database, response.json()["number"])
    assert row["email"] is None
    assert row["response_channel"] == "letter"


@pytest.mark.parametrize(
    "body",
    [
        sheet(email=None),
        sheet(response_channel="letter"),
        sheet(document_number="1234567"),
        sheet(document_type="ruc"),
        sheet(detail="   "),
        sheet(kind="otro"),
        sheet(item_kind=None),
        sheet(claimed_amount_cents=-1),
        sheet(claimed_amount_cents=10.5),
        sheet(guardian={"phone": "+51 999 111 222"}),
    ],
)
def test_incomplete_sheets_are_rejected(
    database: Database, request: pytest.FixtureRequest, body: dict[str, object]
) -> None:
    with api_client(database, address_for(request.node.name)) as client:
        response = client.post("/api/public/complaints", json=body)

    assert response.status_code == 422


async def test_a_client_is_limited_per_hour(
    database: Database, request: pytest.FixtureRequest
) -> None:
    now = datetime(2044, 3, 4, 15, 0, tzinfo=UTC)

    with api_client(database, address_for(request.node.name), FixedClock(now)) as client:
        statuses = [
            client.post("/api/public/complaints", json=sheet()).status_code
            for _ in range(COMPLAINTS_PER_HOUR + 1)
        ]

    assert statuses == [201] * COMPLAINTS_PER_HOUR + [429]
    owner = await asyncpg.connect(database.dsn("casero_owner"))
    try:
        assert (
            await owner.fetchval("SELECT last_number FROM complaint_counters WHERE year = 2044")
            == COMPLAINTS_PER_HOUR
        )
    finally:
        await owner.close()
