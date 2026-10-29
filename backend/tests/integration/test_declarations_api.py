from datetime import UTC, datetime, timedelta
from uuid import uuid7

import asyncpg
import pytest

from api_client import FixedClock
from database import Database
from tax_flows import SUNAT_RUC, add_renter, client_for, pay, register, save_ruc, start_leases

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 27, 15, 0, tzinfo=UTC)
ANA_DNI = "45678912"
OCTOBER = "/api/app/tax/declarations?period=2026-10"


async def test_one_tenant_with_two_leases_has_one_form_with_its_due_date(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with client_for(database, request, FixedClock(NOW)) as client:
        register(client)
        save_ruc(client)
        ana = add_renter(client, "Ana", {"doc_type": "dni", "number": ANA_DNI})
        room, shop = start_leases(client, {"renter_id": ana}, {"renter_id": ana})
        pay(client, room, 45_050, "2026-10-05")
        pay(client, shop, 10_050, "2026-10-20")
        pay(client, room, 30_000, "2026-09-28")
        october = client.get(OCTOBER)
        renters = client.get("/api/app/renters")

    assert october.status_code == 200
    assert october.json() == {
        "period": "2026-10",
        "ruc": SUNAT_RUC,
        "due_on": "2026-11-19",
        "due_status": "known",
        "total_tax_cents": 2_800,
        "declarations": [
            {
                "renter_id": ana,
                "renter_name": "Ana",
                "doc_type": "dni",
                "doc_number": ANA_DNI,
                "incomplete": False,
                "company_tenant": False,
                "lease_ids": sorted([room, shop]),
                "collected_cents": 55_100,
                "old_debt_cents": 0,
                "base_cents": 55_100,
                "tax_cents": 2_800,
            }
        ],
        "untaxed": [],
        "minimum_rent": [],
    }
    assert ANA_DNI not in renters.text


async def test_a_property_rented_under_six_percent_of_its_autovaluo_is_flagged(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with client_for(database, request, FixedClock(NOW)) as client:
        register(client)
        ana = add_renter(client, "Ana")
        luis = add_renter(client, "Luis")
        start_leases(
            client,
            {"renter_id": ana, "control_from_period": "2026-09"},
            house={"name": "Casa grande", "autovaluo_cents": 20_000_000},
        )
        start_leases(
            client,
            {"renter_id": luis},
            house={"name": "Casa chica", "autovaluo_cents": 16_000_000},
        )
        start_leases(
            client,
            {"renter_id": add_renter(client, "Rosa"), "tax_treatment": "unsupported"},
            house={"name": "Cochera", "autovaluo_cents": 50_000_000},
        )
        start_leases(client, {"renter_id": add_renter(client, "Eva")})
        start_leases(
            client,
            {"renter_id": add_renter(client, "Juan"), "monthly_rent_cents": 25_000},
            house={"name": "Cuarto", "autovaluo_cents": 20_000_000, "rented_share_pct": 25},
        )
        september = client.get("/api/app/tax/declarations?period=2026-09").json()
        october = client.get(OCTOBER).json()

    assert [m["property_name"] for m in september["minimum_rent"]] == ["Casa grande"]
    assert [m["property_name"] for m in october["minimum_rent"]] == ["Casa grande"]


async def test_old_debt_untaxed_leases_and_tenants_without_a_document(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with client_for(database, request, FixedClock(NOW)) as client:
        register(client)
        rosa = add_renter(client, "Rosa")
        company = add_renter(client, "Bodega SAC", {"doc_type": "ruc", "number": SUNAT_RUC})
        luis = add_renter(client, "Luis", {"doc_type": "dni", "number": "12345678"})
        with_old_debt, shop, garage = start_leases(
            client,
            {
                "renter_id": rosa,
                "start_date": "2025-06-01",
                "opening_balance_pre_2026_cents": 120_000,
            },
            {"renter_id": company, "tax_treatment": "company_tenant"},
            {"renter_id": luis, "tax_treatment": "unsupported"},
        )
        pay(client, with_old_debt, 150_000, "2026-10-10")
        pay(client, shop, 80_000, "2026-10-06")
        pay(client, garage, 30_000, "2026-10-07")
        october = client.get(OCTOBER).json()

    assert (october["ruc"], october["due_on"], october["due_status"]) == (None, None, "no_ruc")
    assert [
        (
            d["renter_name"],
            d["incomplete"],
            d["company_tenant"],
            d["doc_number"],
            d["collected_cents"],
            d["old_debt_cents"],
            d["tax_cents"],
        )
        for d in october["declarations"]
    ] == [
        ("Bodega SAC", False, True, SUNAT_RUC, 80_000, 0, 4_000),
        ("Rosa", True, False, None, 30_000, 120_000, 1_500),
    ]
    assert october["total_tax_cents"] == 5_500
    assert october["untaxed"] == [
        {"lease_id": garage, "renter_name": "Luis", "collected_cents": 30_000}
    ]


async def test_another_account_sees_none_of_the_declarations(
    database: Database, request: pytest.FixtureRequest
) -> None:
    clock = FixedClock(NOW)
    with client_for(database, request, clock) as ana, client_for(database, request, clock) as luis:
        register(ana)
        register(luis)
        renter = add_renter(ana, "Ana", {"doc_type": "dni", "number": ANA_DNI})
        [lease] = start_leases(ana, {"renter_id": renter})
        pay(ana, lease, 80_000, "2026-10-05")
        seen_by_luis = luis.get(OCTOBER).json()

    assert (seen_by_luis["declarations"], seen_by_luis["untaxed"]) == ([], [])
    assert seen_by_luis["total_tax_cents"] == 0


async def test_the_free_plan_has_no_tax_module(
    database: Database, request: pytest.FixtureRequest
) -> None:
    clock = FixedClock(NOW)
    email = f"{uuid7()}@example.com"
    with client_for(database, request, clock) as client:
        register(client, email)
        owner = await asyncpg.connect(database.dsn("casero_owner"))
        try:
            await owner.execute(
                "UPDATE users SET email_verified_at = $1 WHERE email = $2", NOW, email
            )
        finally:
            await owner.close()
        clock.advance(timedelta(days=29))
        in_trial = client.get(OCTOBER)
        clock.advance(timedelta(days=9))
        lapsed = client.get(OCTOBER)

    assert in_trial.status_code == 200
    assert (lapsed.status_code, lapsed.json()["detail"]) == (403, "tax_module_unavailable")


@pytest.mark.parametrize(
    ("period", "detail"), [("2027-01", "unknown_year"), ("2026-13", None), ("octubre", None)]
)
async def test_a_month_needs_a_valid_period_and_its_years_rules(
    database: Database, request: pytest.FixtureRequest, period: str, detail: str | None
) -> None:
    with client_for(database, request, FixedClock(NOW)) as client:
        register(client)
        response = client.get(f"/api/app/tax/declarations?period={period}")

    assert response.status_code == 422
    if detail:
        assert response.json()["detail"] == detail


def test_declarations_need_a_session(database: Database, request: pytest.FixtureRequest) -> None:
    with client_for(database, request, FixedClock(NOW)) as client:
        response = client.get(OCTOBER)

    assert response.status_code == 401
