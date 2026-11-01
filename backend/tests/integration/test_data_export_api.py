import csv
import io
import json
import zipfile
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid7

import asyncpg
import pytest
from fastapi.testclient import TestClient

import seed
from api_client import FixedClock
from architecture.expected_grants import ACCOUNT_TABLES
from casero.accounts.application.data_export import DataSections
from casero.accounts.infrastructure.data_export import SqlAccountData
from casero.leases.infrastructure.data_export import SqlLeaseData
from casero.ledger.infrastructure.data_export import SqlLedgerData
from casero.properties.infrastructure.data_export import SqlPropertyData
from casero.reminders.infrastructure.data_export import SqlReminderData
from casero.shared.infrastructure.crypto import FieldCipher
from casero.shared.infrastructure.database import create_engine, set_account_context
from casero.tax.infrastructure.data_export import SqlTaxData
from casero.tenant_portal.infrastructure.data_export import SqlTenantPortalData
from database import Database
from tax_flows import add_renter, client_for, pay, register, save_ruc, send, start_leases

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 27, 15, 0, tzinfo=UTC)
EXPORT = "/api/app/exports/my-data.zip"
ANA_DNI = {"doc_type": "dni", "number": "45678912"}
# Left out on purpose: audit_log has field names for security, and push_subscriptions holds
# device keys. message_templates is keyed by kind, so its key can't be looked for.
NOT_LOOKED_FOR = {"audit_log", "push_subscriptions", "message_templates"}


def archive_of(response: Any) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(response.content))


def sections_of(archive: zipfile.ZipFile) -> dict[str, list[dict[str, Any]]]:
    sections: dict[str, list[dict[str, Any]]] = json.loads(archive.read("datos.json"))["secciones"]
    return sections


def csv_rows(archive: zipfile.ZipFile, name: str) -> list[dict[str, str]]:
    text = archive.read(name).decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


def a_landlord_with_data(client: TestClient) -> str:
    register(client)
    save_ruc(client)
    ana = add_renter(client, "Ana Quispe", ANA_DNI)
    [lease] = start_leases(client, {"renter_id": ana})
    body = {
        "id": str(uuid7()),
        "amount_cents": 80_000,
        "received_on": "2026-10-05",
        "method": "yape",
        "note": "=HYPERLINK(1)",
    }
    assert send(client, "POST", f"/api/app/leases/{lease}/payments", body).status_code == 201
    voided = pay(client, lease, 5_000, "2026-10-06")
    send(client, "POST", f"/api/app/payments/{voided}/void", {"reason": "Lo registré mal"})
    return ana


async def test_the_landlord_downloads_everything_as_json_and_csv(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with client_for(database, request, FixedClock(NOW)) as client:
        ana = a_landlord_with_data(client)
        response = client.get(EXPORT)

    assert response.headers["content-type"] == "application/zip"
    assert response.headers["content-disposition"] == 'attachment; filename="casero-mis-datos.zip"'
    assert response.headers["cache-control"] == "no-store"
    archive = archive_of(response)
    sections = sections_of(archive)
    assert set(archive.namelist()) == {"datos.json", *(f"{name}.csv" for name in sections)}
    assert sections["cuenta"][0]["ruc"] == "20131312955"
    [renter] = sections["inquilinos"]
    assert (renter["id"], renter["nombre"]) == (ana, "Ana Quispe")
    assert (renter["tipo_de_documento"], renter["numero_de_documento"]) == ("dni", "45678912")
    good, bad = sections["pagos"]
    assert (good["monto_centimos"], good["fecha_de_cobro"]) == (80_000, "2026-10-05")
    assert good["anulado_el"] is None
    assert bad["motivo_de_anulacion"] == "Lo registré mal"
    assert csv_rows(archive, "inquilinos.csv")[0]["numero_de_documento"] == "45678912"
    assert csv_rows(archive, "pagos.csv")[0]["nota"] == "'=HYPERLINK(1)"
    assert sorted(row["documento"] for row in sections["aceptaciones_legales"]) == [
        "privacy",
        "sensitive_consent",
        "terms",
    ]


async def test_nothing_secret_leaves_with_the_data(
    database: Database, request: pytest.FixtureRequest
) -> None:
    with client_for(database, request, FixedClock(NOW)) as client:
        a_landlord_with_data(client)
        response = client.get(EXPORT)

    exported = archive_of(response).read("datos.json")
    for secret in (b"hash", b"hmac", b"token", b"nonce", b"doc_enc", b"storage_key", b"password"):
        assert secret not in exported, secret


async def test_each_export_is_audited_and_works_on_a_blocked_account(
    database: Database, request: pytest.FixtureRequest
) -> None:
    clock = FixedClock(NOW)
    with client_for(database, request, clock) as client:
        ana = a_landlord_with_data(client)
        clock.advance(timedelta(minutes=1))
        send(client, "POST", "/api/app/legal/consent-withdrawal")
        blocked = client.get("/api/app/account")
        response = client.get(EXPORT)

    assert blocked.status_code == 403
    assert response.status_code == 200
    owner = await asyncpg.connect(database.dsn("casero_owner"))
    try:
        audited = await owner.fetch(
            "SELECT a.action FROM audit_log a JOIN renters r ON r.account_id = a.account_id"
            " WHERE r.id = $1 AND a.action = 'export.my_data'",
            UUID(ana),
        )
    finally:
        await owner.close()
    assert len(audited) == 1


async def test_another_accounts_data_stays_out(
    database: Database, request: pytest.FixtureRequest
) -> None:
    clock = FixedClock(NOW)
    with client_for(database, request, clock) as ana, client_for(database, request, clock) as luis:
        a_landlord_with_data(ana)
        register(luis)
        response = luis.get(EXPORT)

    archive = archive_of(response)
    assert b"Ana Quispe" not in archive.read("datos.json")
    assert sections_of(archive)["inquilinos"] == []
    assert sections_of(archive)["pagos"] == []


def test_the_export_needs_a_session(database: Database, request: pytest.FixtureRequest) -> None:
    with client_for(database, request, FixedClock(NOW)) as client:
        assert client.get(EXPORT).status_code == 401


async def test_every_account_table_reaches_the_export_or_is_left_out_on_purpose(
    database: Database,
) -> None:
    owner = await asyncpg.connect(database.dsn("casero_owner"))
    try:
        seeded = await seed.seed_account(owner, lease_count=1)
    finally:
        await owner.close()
    engine = create_engine(
        database.dsn("casero_app").replace("postgresql://", "postgresql+asyncpg://", 1)
    )
    try:
        async with engine.begin() as connection:
            await set_account_context(connection, seeded.account_id)
            modules: list[DataSections] = [
                SqlAccountData(connection),
                SqlPropertyData(connection),
                SqlLeaseData(connection, FieldCipher({"test": bytes(32)}, "test")),
                SqlLedgerData(connection),
                SqlTaxData(connection),
                SqlReminderData(connection),
                SqlTenantPortalData(connection),
            ]
            sections = [s for module in modules for s in await module.sections(seeded.account_id)]
    finally:
        await engine.dispose()

    exported = json.dumps([section.rows for section in sections])
    missing = sorted(
        table
        for table in ACCOUNT_TABLES - NOT_LOOKED_FOR
        for key in seeded.keys.get(table, {f"nothing seeded for {table}"})
        if key not in exported
    )
    assert missing == []
    assert any(
        section.name == "plantillas_de_mensajes" and ("friendly", "Hola") in section.rows
        for section in sections
    )
