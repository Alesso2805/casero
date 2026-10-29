from typing import Any
from uuid import uuid7

import pytest
from fastapi.testclient import TestClient

from api_client import FixedClock, address_for, api_client
from database import Database

CSRF = "__Host-casero_csrf"
SUNAT_RUC = "20131312955"


def send(client: TestClient, method: str, path: str, body: object = None) -> Any:
    return client.request(method, path, json=body, headers={"X-CSRF-Token": client.cookies[CSRF]})


def register(client: TestClient, email: str | None = None) -> None:
    client.get("/api/public/csrf")
    registered = send(
        client,
        "POST",
        "/api/public/registration",
        {
            "email": email or f"{uuid7()}@example.com",
            "password": "una clave bien larga",
            "display_name": "Casera",
            "accept_terms_and_privacy": True,
            "consent_sensitive_data": True,
        },
    )
    assert registered.status_code == 201


def save_ruc(client: TestClient) -> None:
    profile = {
        "display_name": "Casera",
        "taxpayer_kind": "person",
        "ruc": SUNAT_RUC,
        "good_taxpayer": False,
        "daily_digest": True,
    }
    assert send(client, "PUT", "/api/app/account/profile", profile).status_code == 200


def add_renter(client: TestClient, name: str, document: dict[str, str] | None = None) -> str:
    body: dict[str, object] = {"full_name": name}
    if document:
        body["document"] = document
    renter = send(client, "POST", "/api/app/renters", body)
    assert renter.status_code == 201
    return str(renter.json()["id"])


def start_leases(
    client: TestClient, *terms: dict[str, object], house: dict[str, object] | None = None
) -> list[str]:
    units = [{"name": f"Cuarto {n}", "kind": "room"} for n in range(len(terms))]
    details = {"name": "Casa", "ownership": "sole", "units": units, **(house or {})}
    created_house = send(client, "POST", "/api/app/properties", details).json()
    ids = []
    for unit, overrides in zip(created_house["units"], terms, strict=True):
        lease = {
            "id": str(uuid7()),
            "unit_id": unit["id"],
            "monthly_rent_cents": 80_000,
            "due_day": 5,
            "start_date": "2026-03-01",
            "control_from_period": "2026-10",
            "tax_treatment": "standard",
            **overrides,
        }
        created = send(client, "POST", "/api/app/leases", lease)
        assert created.status_code == 201, created.json()
        ids.append(str(lease["id"]))
    return ids


def pay(client: TestClient, lease_id: str, cents: int, on: str) -> None:
    body = {"id": str(uuid7()), "amount_cents": cents, "received_on": on, "method": "yape"}
    assert send(client, "POST", f"/api/app/leases/{lease_id}/payments", body).status_code == 201


def client_for(database: Database, request: pytest.FixtureRequest, clock: FixedClock) -> Any:
    return api_client(database, address_for(request.node.name), clock, registration_mode="open")
