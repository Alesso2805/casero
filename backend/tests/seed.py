import json
import os
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from uuid import UUID, uuid7

import asyncpg

TERMS_DOCUMENT_ID = UUID("01a175b4-8f38-727d-a7dc-40a7a7b3647d")
SEEDED_AT = datetime(2026, 10, 25, 15, 0, tzinfo=UTC)
SEEDED_ON = date(2026, 10, 25)

KEY_COLUMNS = {
    "charge_voids": "charge_id",
    "payment_voids": "payment_id",
    "deposit_voids": "deposit_id",
    "deposit_movement_voids": "deposit_movement_id",
    "tax_payment_voids": "tax_payment_id",
    "message_templates": "account_id::text || ':' || kind",
}

LEASE_SCOPED_TABLES = frozenset(
    {
        "units",
        "renters",
        "properties",
        "leases",
        "lease_rent_changes",
        "files",
        "deposits",
        "charges",
        "charge_voids",
        "payments",
        "payment_voids",
        "deposit_voids",
        "deposit_movements",
        "deposit_movement_voids",
        "voucher_submissions",
        "tenant_links",
    }
)
TENANT_ACCOUNT_TABLES = frozenset({"accounts", "subscriptions"})


@dataclass
class SeededAccount:
    account_id: UUID
    user_id: UUID
    email: str
    lease_ids: list[UUID] = field(default_factory=list)
    token_hashes: dict[UUID, bytes] = field(default_factory=dict)
    keys: dict[str, set[str]] = field(default_factory=dict)
    lease_keys: dict[UUID, dict[str, set[str]]] = field(default_factory=dict)

    def add(self, table: str, key: object, lease_id: UUID | None = None) -> None:
        self.keys.setdefault(table, set()).add(str(key))
        if lease_id is not None:
            self.lease_keys.setdefault(lease_id, {}).setdefault(table, set()).add(str(key))


async def visible_keys(connection: asyncpg.Connection, table: str) -> set[str]:
    key = KEY_COLUMNS.get(table, "id")
    return {
        row["key"] for row in await connection.fetch(f"SELECT ({key})::text AS key FROM {table}")
    }


async def set_context(
    connection: asyncpg.Connection,
    account_id: UUID | None,
    context: str | None = None,
    lease_id: UUID | None = None,
) -> None:
    await connection.execute(
        "SELECT set_config('app.account_id', $1, true), set_config('app.context', $2, true),"
        " set_config('app.lease_id', $3, true)",
        str(account_id) if account_id else "",
        context or "",
        str(lease_id) if lease_id else "",
    )


async def seed_account(owner: asyncpg.Connection, lease_count: int) -> SeededAccount:
    account_id, user_id, property_id = uuid7(), uuid7(), uuid7()
    seeded = SeededAccount(account_id, user_id, f"{user_id}@example.test")
    await owner.execute(
        "INSERT INTO users (id, email, password_hash, created_at) VALUES ($1, $2, 'x', $3)",
        user_id,
        seeded.email,
        SEEDED_AT,
    )
    await owner.execute(
        "INSERT INTO accounts (id, display_name, created_at) VALUES ($1, 'Cuenta de prueba', $2)",
        account_id,
        SEEDED_AT,
    )
    seeded.add("accounts", account_id)
    await owner.execute(
        "INSERT INTO account_members (account_id, user_id, role) VALUES ($1, $2, 'owner')",
        account_id,
        user_id,
    )
    rows = {
        "legal_acceptances": (
            "INSERT INTO legal_acceptances (id, account_id, user_id, document_id, accepted_at,"
            " ip_hash) VALUES ($1, $2, $3, $4, $5, $6)",
            (user_id, TERMS_DOCUMENT_ID, SEEDED_AT, os.urandom(32)),
        ),
        "legal_withdrawals": (
            "INSERT INTO legal_withdrawals (id, account_id, user_id, document_id, withdrawn_at)"
            " VALUES ($1, $2, $3, $4, $5)",
            (user_id, TERMS_DOCUMENT_ID, SEEDED_AT),
        ),
        "subscriptions": (
            "INSERT INTO subscriptions (id, account_id, plan_code, starts_at)"
            " VALUES ($1, $2, 'casero', $3)",
            (SEEDED_ON,),
        ),
        "subscription_payments": (
            "INSERT INTO subscription_payments (id, account_id, amount_cents, paid_on, method,"
            " boleta_number, months) VALUES ($1, $2, 19000, $3, 'yape', 'B001-1', 12)",
            (SEEDED_ON,),
        ),
        "push_subscriptions": (
            "INSERT INTO push_subscriptions (id, account_id, user_id, endpoint, keys, created_at)"
            " VALUES ($1, $2, $3, 'https://push.example.test', $4, $5)",
            (user_id, json.dumps({}), SEEDED_AT),
        ),
        "audit_log": (
            "INSERT INTO audit_log (id, account_id, actor_user_id, action, entity, changed_fields,"
            " at) VALUES ($1, $2, $3, 'create', 'lease', '{}', $4)",
            (user_id, SEEDED_AT),
        ),
    }
    for table, (sql, values) in rows.items():
        row_id = uuid7()
        await owner.execute(sql, row_id, account_id, *values)
        seeded.add(table, row_id)
    await owner.execute(
        "INSERT INTO properties (id, account_id, name, ownership) VALUES ($1, $2, 'Casa', 'sole')",
        property_id,
        account_id,
    )
    seeded.add("properties", property_id)
    await owner.execute(
        "INSERT INTO message_templates (account_id, kind, body) VALUES ($1, 'friendly', 'Hola')",
        account_id,
    )
    seeded.add("message_templates", f"{account_id}:friendly")
    for _ in range(lease_count):
        await seed_lease(owner, seeded, user_id, property_id)
    return seeded


async def seed_lease(
    owner: asyncpg.Connection, seeded: SeededAccount, user_id: UUID, property_id: UUID
) -> None:
    account_id = seeded.account_id
    unit_id, renter_id, lease_id = uuid7(), uuid7(), uuid7()
    seeded.lease_ids.append(lease_id)
    token_hash = os.urandom(32)
    seeded.token_hashes[lease_id] = token_hash
    seeded.add("properties", property_id, lease_id)
    ids = {
        table: uuid7()
        for table in (
            "lease_rent_changes",
            "files",
            "deposits",
            "rent",
            "voided_rent",
            "payment",
            "guarantee_payment",
            "deposit_movements",
            "voucher_submissions",
            "tenant_links",
            "reminder_logs",
            "tax_payments",
        )
    }
    statements = [
        (
            "units",
            unit_id,
            "INSERT INTO units (id, account_id, property_id, name, kind)"
            " VALUES ($1, $2, $3, 'Cuarto', 'room')",
            (property_id,),
        ),
        (
            "renters",
            renter_id,
            "INSERT INTO renters (id, account_id, full_name) VALUES ($1, $2, 'Inquilino')",
            (),
        ),
        (
            "leases",
            lease_id,
            "INSERT INTO leases (id, account_id, unit_id, renter_id, due_day, start_date,"
            " control_from_period, tax_treatment, created_at)"
            " VALUES ($1, $2, $3, $4, 5, $5, '2026-10', 'standard', $6)",
            (unit_id, renter_id, SEEDED_ON, SEEDED_AT),
        ),
        (
            "lease_rent_changes",
            ids["lease_rent_changes"],
            "INSERT INTO lease_rent_changes (id, account_id, lease_id, monthly_rent_cents,"
            " effective_period, created_by, created_at)"
            " VALUES ($1, $2, $3, 50000, '2026-10', $4, $5)",
            (lease_id, user_id, SEEDED_AT),
        ),
        (
            "files",
            ids["files"],
            "INSERT INTO files (id, account_id, purpose, storage_key, mime, size_bytes, sha256,"
            " created_at) VALUES ($1, $2, 'voucher', $3, 'image/png', 100, $4, $5)",
            (f"{account_id}/{ids['files']}", os.urandom(32), SEEDED_AT),
        ),
        (
            "deposits",
            ids["deposits"],
            "INSERT INTO deposits (id, account_id, lease_id, amount_cents, received_on, created_at)"
            " VALUES ($1, $2, $3, 50000, $4, $5)",
            (lease_id, SEEDED_ON, SEEDED_AT),
        ),
        (
            "charges",
            ids["rent"],
            "INSERT INTO charges (id, account_id, lease_id, kind, period, amount_cents, due_date,"
            " created_at) VALUES ($1, $2, $3, 'rent', '2026-10', 50000, $4, $5)",
            (lease_id, SEEDED_ON, SEEDED_AT),
        ),
        (
            "charges",
            ids["voided_rent"],
            "INSERT INTO charges (id, account_id, lease_id, kind, period, amount_cents, due_date,"
            " created_at) VALUES ($1, $2, $3, 'rent', '2026-11', 50000, $4, $5)",
            (lease_id, SEEDED_ON, SEEDED_AT),
        ),
        (
            "charge_voids",
            ids["voided_rent"],
            "INSERT INTO charge_voids (charge_id, account_id, reason, voided_by, voided_at)"
            " VALUES ($1, $2, 'error', $3, $4)",
            (user_id, SEEDED_AT),
        ),
        (
            "payments",
            ids["payment"],
            "INSERT INTO payments (id, account_id, lease_id, amount_cents, received_on, method,"
            " source, created_by, created_at) VALUES ($1, $2, $3, 20000, $4, 'cash', 'landlord',"
            " $5, $6)",
            (lease_id, SEEDED_ON, user_id, SEEDED_AT),
        ),
        (
            "payments",
            ids["guarantee_payment"],
            "INSERT INTO payments (id, account_id, lease_id, amount_cents, received_on, method,"
            " deposit_id, source, created_by, created_at) VALUES ($1, $2, $3, 10000, $4,"
            " 'guarantee', $5, 'landlord', $6, $7)",
            (lease_id, SEEDED_ON, ids["deposits"], user_id, SEEDED_AT),
        ),
        (
            "payment_voids",
            ids["guarantee_payment"],
            "INSERT INTO payment_voids (payment_id, account_id, reason, voided_by, voided_at)"
            " VALUES ($1, $2, 'error', $3, $4)",
            (user_id, SEEDED_AT),
        ),
        (
            "deposit_voids",
            ids["deposits"],
            "INSERT INTO deposit_voids (deposit_id, account_id, reason, voided_by, voided_at)"
            " VALUES ($1, $2, 'error', $3, $4)",
            (user_id, SEEDED_AT),
        ),
        (
            "deposit_movements",
            ids["deposit_movements"],
            "INSERT INTO deposit_movements (id, account_id, deposit_id, amount_cents, on_date,"
            " created_by, created_at) VALUES ($1, $2, $3, 1000, $4, $5, $6)",
            (ids["deposits"], SEEDED_ON, user_id, SEEDED_AT),
        ),
        (
            "deposit_movement_voids",
            ids["deposit_movements"],
            "INSERT INTO deposit_movement_voids (deposit_movement_id, account_id, reason,"
            " voided_by,"
            " voided_at) VALUES ($1, $2, 'error', $3, $4)",
            (user_id, SEEDED_AT),
        ),
        (
            "voucher_submissions",
            ids["voucher_submissions"],
            "INSERT INTO voucher_submissions (id, account_id, lease_id, file_id, declared_cents,"
            " declared_on, status, created_at) VALUES ($1, $2, $3, $4, 50000, $5, 'pending', $6)",
            (lease_id, ids["files"], SEEDED_ON, SEEDED_AT),
        ),
        (
            "tenant_links",
            ids["tenant_links"],
            "INSERT INTO tenant_links (id, account_id, lease_id, nonce, key_id, token_hash,"
            " created_at) VALUES ($1, $2, $3, $4, 'k1', $5, $6)",
            (lease_id, os.urandom(16), token_hash, SEEDED_AT),
        ),
        (
            "reminder_logs",
            ids["reminder_logs"],
            "INSERT INTO reminder_logs (id, account_id, kind, charge_id, channel, created_at)"
            " VALUES ($1, $2, 'rent', $3, 'whatsapp_link', $4)",
            (ids["rent"], SEEDED_AT),
        ),
        (
            "tax_payments",
            ids["tax_payments"],
            "INSERT INTO tax_payments (id, account_id, period, renter_doc_hmac, renter_id,"
            " amount_cents, paid_on, order_number, created_by, created_at)"
            " VALUES ($1, $2, '2026-10', $3, $4, 2500, $5, 'ORD-1', $6, $7)",
            (os.urandom(32), renter_id, SEEDED_ON, user_id, SEEDED_AT),
        ),
        (
            "tax_payment_voids",
            ids["tax_payments"],
            "INSERT INTO tax_payment_voids (tax_payment_id, account_id, reason, voided_by,"
            " voided_at)"
            " VALUES ($1, $2, 'error', $3, $4)",
            (user_id, SEEDED_AT),
        ),
    ]
    for table, key, sql, values in statements:
        await owner.execute(sql, key, account_id, *values)
        lease = lease_id if table in LEASE_SCOPED_TABLES else None
        seeded.add(table, key, lease)


def expected_tenant_keys(seeded: SeededAccount, lease_id: UUID, table: str) -> set[str]:
    if table in TENANT_ACCOUNT_TABLES:
        return seeded.keys[table]
    if table in LEASE_SCOPED_TABLES:
        return seeded.lease_keys[lease_id].get(table, set())
    return set()
