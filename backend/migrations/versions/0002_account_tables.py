from casero.shared.infrastructure.migrations import execute_script

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

PERIOD = "CHECK ({column} ~ '^[0-9]{{4}}-(0[1-9]|1[0-2])$')"
CURRENT_ACCOUNT = "NULLIF(current_setting('app.account_id', true), '')::uuid"
CURRENT_LEASE = "NULLIF(current_setting('app.lease_id', true), '')::uuid"
OUTSIDE_TENANT_CONTEXT = "current_setting('app.context', true) IS DISTINCT FROM 'tenant'"

TABLES = f"""
CREATE TABLE accounts (
    id uuid PRIMARY KEY,
    display_name text,
    taxpayer_kind text NOT NULL DEFAULT 'person' CHECK (taxpayer_kind IN ('person', 'estate')),
    ruc text CHECK (ruc ~ '^[0-9]{{11}}$'),
    ruc_group text CHECK (ruc_group IN ('0', '1', '2-3', '4-5', '6-7', '8-9', 'bc')),
    daily_digest boolean NOT NULL DEFAULT false,
    deletion_requested_at timestamptz,
    deletion_scheduled_for date,
    deletion_contact_enc text,
    purged_at date,
    created_at timestamptz NOT NULL,
    CHECK (purged_at IS NOT NULL OR display_name IS NOT NULL),
    CHECK ((ruc IS NULL) = (ruc_group IS NULL)),
    CHECK ((deletion_requested_at IS NULL) = (deletion_scheduled_for IS NULL))
);

ALTER TABLE account_members
    ADD FOREIGN KEY (account_id) REFERENCES accounts (id);

CREATE TABLE legal_acceptances (
    id uuid PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES accounts (id),
    user_id uuid NOT NULL REFERENCES users (id),
    document_id uuid NOT NULL REFERENCES legal_documents (id),
    accepted_at timestamptz NOT NULL,
    ip_hash bytea NOT NULL,
    UNIQUE (account_id, id)
);

CREATE TABLE legal_withdrawals (
    id uuid PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES accounts (id),
    user_id uuid NOT NULL REFERENCES users (id),
    document_id uuid NOT NULL REFERENCES legal_documents (id),
    withdrawn_at timestamptz NOT NULL,
    UNIQUE (account_id, id)
);

CREATE TABLE subscriptions (
    id uuid PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES accounts (id),
    plan_code text NOT NULL REFERENCES plans (code),
    starts_at date NOT NULL,
    trial_ends_at date,
    ends_at date,
    ended_at date,
    founder boolean NOT NULL DEFAULT false,
    UNIQUE (account_id, id)
);
CREATE UNIQUE INDEX subscriptions_one_open_per_account
    ON subscriptions (account_id) WHERE ended_at IS NULL;

CREATE TABLE subscription_payments (
    id uuid PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES accounts (id),
    amount_cents bigint NOT NULL CHECK (amount_cents > 0),
    paid_on date NOT NULL,
    method text NOT NULL CHECK (method IN ('yape', 'transfer')),
    boleta_number text NOT NULL,
    months integer NOT NULL CHECK (months > 0),
    UNIQUE (account_id, id)
);

CREATE TABLE push_subscriptions (
    id uuid PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES accounts (id),
    user_id uuid NOT NULL REFERENCES users (id),
    endpoint text NOT NULL,
    keys jsonb NOT NULL,
    created_at timestamptz NOT NULL,
    revoked_at timestamptz,
    UNIQUE (account_id, id)
);

CREATE TABLE properties (
    id uuid PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES accounts (id),
    name text NOT NULL,
    address_line text,
    district text,
    ownership text NOT NULL
        CHECK (ownership IN ('sole', 'co_owned', 'conjugal_option', 'conjugal_split', 'estate')),
    autovaluo_cents bigint CHECK (autovaluo_cents > 0),
    rented_share_pct integer NOT NULL DEFAULT 100 CHECK (rented_share_pct BETWEEN 1 AND 100),
    archived_at timestamptz,
    UNIQUE (account_id, id)
);

CREATE TABLE units (
    id uuid PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES accounts (id),
    property_id uuid NOT NULL,
    name text NOT NULL,
    kind text NOT NULL
        CHECK (kind IN ('room', 'mini_apartment', 'apartment', 'shop', 'parking', 'other')),
    archived_at timestamptz,
    UNIQUE (account_id, id),
    FOREIGN KEY (account_id, property_id) REFERENCES properties (account_id, id)
);

CREATE TABLE renters (
    id uuid PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES accounts (id),
    full_name text NOT NULL,
    phone_e164 text CHECK (phone_e164 ~ '^\\+[1-9][0-9]{{6,14}}$'),
    email text,
    doc_type text CHECK (doc_type IN ('dni', 'ce', 'passport', 'ruc')),
    doc_enc text,
    doc_hmac bytea,
    doc_last4 text CHECK (doc_last4 ~ '^[0-9A-Z]{{1,4}}$'),
    UNIQUE (account_id, id),
    CHECK (
        (doc_type IS NULL) = (doc_enc IS NULL)
        AND (doc_enc IS NULL) = (doc_hmac IS NULL)
        AND (doc_hmac IS NULL) = (doc_last4 IS NULL)
    )
);

CREATE TABLE leases (
    id uuid PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES accounts (id),
    unit_id uuid NOT NULL,
    renter_id uuid NOT NULL,
    due_day integer NOT NULL CHECK (due_day BETWEEN 1 AND 31),
    start_date date NOT NULL,
    control_from_period text NOT NULL {PERIOD.format(column="control_from_period")},
    end_date date,
    ended_at date,
    tax_treatment text NOT NULL
        CHECK (tax_treatment IN ('standard', 'company_tenant', 'unsupported')),
    tools_enabled boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL,
    UNIQUE (account_id, id),
    FOREIGN KEY (account_id, unit_id) REFERENCES units (account_id, id),
    FOREIGN KEY (account_id, renter_id) REFERENCES renters (account_id, id),
    CHECK (end_date >= start_date)
);
CREATE UNIQUE INDEX leases_one_active_per_unit ON leases (unit_id) WHERE ended_at IS NULL;

CREATE TABLE lease_rent_changes (
    id uuid PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES accounts (id),
    lease_id uuid NOT NULL,
    monthly_rent_cents bigint NOT NULL CHECK (monthly_rent_cents > 0),
    effective_period text NOT NULL {PERIOD.format(column="effective_period")},
    created_by uuid NOT NULL REFERENCES users (id),
    created_at timestamptz NOT NULL,
    UNIQUE (account_id, id),
    FOREIGN KEY (account_id, lease_id) REFERENCES leases (account_id, id)
);

CREATE TABLE files (
    id uuid PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES accounts (id),
    purpose text NOT NULL CHECK (purpose = 'voucher'),
    storage_key text NOT NULL UNIQUE,
    mime text NOT NULL CHECK (mime IN ('image/jpeg', 'image/png', 'application/pdf')),
    size_bytes integer NOT NULL CHECK (size_bytes BETWEEN 1 AND 5242880),
    sha256 bytea NOT NULL,
    created_at timestamptz NOT NULL,
    purged_at date,
    UNIQUE (account_id, id)
);
CREATE UNIQUE INDEX files_one_live_copy_per_hash
    ON files (account_id, sha256) WHERE purged_at IS NULL;

CREATE TABLE deposits (
    id uuid PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES accounts (id),
    lease_id uuid NOT NULL,
    amount_cents bigint NOT NULL CHECK (amount_cents > 0),
    received_on date NOT NULL,
    note text,
    created_at timestamptz NOT NULL,
    UNIQUE (account_id, id),
    FOREIGN KEY (account_id, lease_id) REFERENCES leases (account_id, id)
);

CREATE TABLE charges (
    id uuid PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES accounts (id),
    lease_id uuid NOT NULL,
    kind text NOT NULL CHECK (kind IN ('rent', 'rent_correction', 'opening_balance', 'adjustment')),
    period text {PERIOD.format(column="period")},
    amount_cents bigint NOT NULL,
    due_date date NOT NULL,
    corrects_charge_id uuid UNIQUE,
    pre_2026 boolean,
    created_by uuid REFERENCES users (id),
    created_at timestamptz NOT NULL,
    UNIQUE (account_id, id),
    FOREIGN KEY (account_id, lease_id) REFERENCES leases (account_id, id),
    FOREIGN KEY (account_id, corrects_charge_id) REFERENCES charges (account_id, id),
    CHECK (CASE WHEN kind = 'adjustment' THEN amount_cents <> 0 ELSE amount_cents > 0 END),
    CHECK (kind NOT IN ('rent', 'rent_correction') OR period IS NOT NULL),
    CHECK (kind <> 'opening_balance' OR period IS NULL),
    CHECK ((kind = 'opening_balance') = (pre_2026 IS NOT NULL)),
    CHECK ((kind = 'rent_correction') = (corrects_charge_id IS NOT NULL))
);
CREATE UNIQUE INDEX charges_one_rent_per_period ON charges (lease_id, period) WHERE kind = 'rent';
CREATE UNIQUE INDEX charges_one_opening_balance_per_era
    ON charges (lease_id, pre_2026) WHERE kind = 'opening_balance';

CREATE TABLE charge_voids (
    charge_id uuid PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES accounts (id),
    reason text NOT NULL,
    voided_by uuid NOT NULL REFERENCES users (id),
    voided_at timestamptz NOT NULL,
    FOREIGN KEY (account_id, charge_id) REFERENCES charges (account_id, id)
);

CREATE TABLE payments (
    id uuid PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES accounts (id),
    lease_id uuid NOT NULL,
    amount_cents bigint NOT NULL CHECK (amount_cents > 0),
    received_on date NOT NULL,
    method text NOT NULL
        CHECK (method IN ('cash', 'yape', 'plin', 'transfer', 'bank_deposit', 'guarantee')),
    deposit_id uuid,
    note text,
    source text NOT NULL CHECK (source IN ('landlord', 'tenant_voucher')),
    created_by uuid NOT NULL REFERENCES users (id),
    created_at timestamptz NOT NULL,
    UNIQUE (account_id, id),
    FOREIGN KEY (account_id, lease_id) REFERENCES leases (account_id, id),
    FOREIGN KEY (account_id, deposit_id) REFERENCES deposits (account_id, id),
    CHECK ((method = 'guarantee') = (deposit_id IS NOT NULL))
);
CREATE INDEX payments_by_received_on ON payments (account_id, received_on);

CREATE TABLE payment_voids (
    payment_id uuid PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES accounts (id),
    reason text NOT NULL,
    voided_by uuid NOT NULL REFERENCES users (id),
    voided_at timestamptz NOT NULL,
    FOREIGN KEY (account_id, payment_id) REFERENCES payments (account_id, id)
);

CREATE TABLE deposit_voids (
    deposit_id uuid PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES accounts (id),
    reason text NOT NULL,
    voided_by uuid NOT NULL REFERENCES users (id),
    voided_at timestamptz NOT NULL,
    FOREIGN KEY (account_id, deposit_id) REFERENCES deposits (account_id, id)
);

CREATE TABLE deposit_movements (
    id uuid PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES accounts (id),
    deposit_id uuid NOT NULL,
    amount_cents bigint NOT NULL CHECK (amount_cents > 0),
    on_date date NOT NULL,
    created_by uuid NOT NULL REFERENCES users (id),
    created_at timestamptz NOT NULL,
    UNIQUE (account_id, id),
    FOREIGN KEY (account_id, deposit_id) REFERENCES deposits (account_id, id)
);

CREATE TABLE deposit_movement_voids (
    deposit_movement_id uuid PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES accounts (id),
    reason text NOT NULL,
    voided_by uuid NOT NULL REFERENCES users (id),
    voided_at timestamptz NOT NULL,
    FOREIGN KEY (account_id, deposit_movement_id) REFERENCES deposit_movements (account_id, id)
);

CREATE TABLE voucher_submissions (
    id uuid PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES accounts (id),
    lease_id uuid NOT NULL,
    file_id uuid NOT NULL,
    declared_cents bigint NOT NULL CHECK (declared_cents > 0),
    declared_on date NOT NULL,
    status text NOT NULL CHECK (status IN ('pending', 'confirmed', 'rejected')),
    reject_reason text,
    payment_id uuid UNIQUE,
    reviewed_by uuid REFERENCES users (id),
    reviewed_at timestamptz,
    created_at timestamptz NOT NULL,
    UNIQUE (account_id, id),
    FOREIGN KEY (account_id, lease_id) REFERENCES leases (account_id, id),
    FOREIGN KEY (account_id, file_id) REFERENCES files (account_id, id),
    FOREIGN KEY (account_id, payment_id) REFERENCES payments (account_id, id),
    CHECK ((status = 'confirmed') = (payment_id IS NOT NULL)),
    CHECK ((status = 'rejected') = (reject_reason IS NOT NULL)),
    CHECK ((status = 'pending') = (reviewed_at IS NULL))
);

CREATE TABLE tenant_links (
    id uuid PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES accounts (id),
    lease_id uuid NOT NULL,
    nonce bytea NOT NULL,
    key_id text NOT NULL,
    token_hash bytea NOT NULL UNIQUE,
    created_at timestamptz NOT NULL,
    revoked_at timestamptz,
    last_used_at timestamptz,
    UNIQUE (account_id, id),
    FOREIGN KEY (account_id, lease_id) REFERENCES leases (account_id, id)
);
CREATE UNIQUE INDEX tenant_links_one_active_per_lease
    ON tenant_links (lease_id) WHERE revoked_at IS NULL;

CREATE TABLE message_templates (
    account_id uuid NOT NULL REFERENCES accounts (id),
    kind text NOT NULL CHECK (kind IN ('friendly', 'due_today', 'overdue')),
    body text NOT NULL,
    PRIMARY KEY (account_id, kind)
);

CREATE TABLE reminder_logs (
    id uuid PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES accounts (id),
    kind text NOT NULL CHECK (kind IN ('rent', 'tax_due')),
    charge_id uuid,
    period text {PERIOD.format(column="period")},
    renter_id uuid,
    renter_doc_hmac bytea,
    channel text NOT NULL CHECK (channel IN ('whatsapp_link', 'email', 'push')),
    created_at timestamptz NOT NULL,
    UNIQUE (account_id, id),
    FOREIGN KEY (account_id, charge_id) REFERENCES charges (account_id, id),
    FOREIGN KEY (account_id, renter_id) REFERENCES renters (account_id, id),
    CHECK (
        (kind = 'rent' AND charge_id IS NOT NULL)
        OR (kind = 'tax_due' AND charge_id IS NULL AND period IS NOT NULL AND renter_id IS NOT NULL)
    )
);

CREATE TABLE tax_payments (
    id uuid PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES accounts (id),
    period text NOT NULL {PERIOD.format(column="period")},
    renter_doc_hmac bytea NOT NULL,
    renter_id uuid NOT NULL,
    amount_cents bigint NOT NULL CHECK (amount_cents > 0),
    paid_on date NOT NULL,
    order_number text NOT NULL,
    created_by uuid NOT NULL REFERENCES users (id),
    created_at timestamptz NOT NULL,
    UNIQUE (account_id, id),
    FOREIGN KEY (account_id, renter_id) REFERENCES renters (account_id, id)
);

CREATE TABLE tax_payment_voids (
    tax_payment_id uuid PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES accounts (id),
    reason text NOT NULL,
    voided_by uuid NOT NULL REFERENCES users (id),
    voided_at timestamptz NOT NULL,
    FOREIGN KEY (account_id, tax_payment_id) REFERENCES tax_payments (account_id, id)
);

CREATE TABLE audit_log (
    id uuid PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES accounts (id),
    actor_user_id uuid REFERENCES users (id),
    action text NOT NULL,
    entity text NOT NULL,
    entity_id uuid,
    changed_fields text[] NOT NULL,
    at timestamptz NOT NULL,
    UNIQUE (account_id, id)
);
"""

ACCOUNT_TABLES = (
    "accounts",
    "legal_acceptances",
    "legal_withdrawals",
    "subscriptions",
    "subscription_payments",
    "push_subscriptions",
    "properties",
    "units",
    "renters",
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
    "message_templates",
    "reminder_logs",
    "tax_payments",
    "tax_payment_voids",
    "audit_log",
)

TENANT_VISIBLE_TABLES = ("accounts", "subscriptions")

TENANT_SCOPE = {
    "leases": f"id = {CURRENT_LEASE}",
    "lease_rent_changes": f"lease_id = {CURRENT_LEASE}",
    "charges": f"lease_id = {CURRENT_LEASE}",
    "payments": f"lease_id = {CURRENT_LEASE}",
    "deposits": f"lease_id = {CURRENT_LEASE}",
    "voucher_submissions": f"lease_id = {CURRENT_LEASE}",
    "tenant_links": f"lease_id = {CURRENT_LEASE}",
    "charge_voids": "EXISTS (SELECT 1 FROM charges c WHERE c.id = charge_voids.charge_id"
    f" AND c.lease_id = {CURRENT_LEASE})",
    "payment_voids": "EXISTS (SELECT 1 FROM payments p WHERE p.id = payment_voids.payment_id"
    f" AND p.lease_id = {CURRENT_LEASE})",
    "deposit_voids": "EXISTS (SELECT 1 FROM deposits d WHERE d.id = deposit_voids.deposit_id"
    f" AND d.lease_id = {CURRENT_LEASE})",
    "deposit_movements": "EXISTS (SELECT 1 FROM deposits d"
    f" WHERE d.id = deposit_movements.deposit_id AND d.lease_id = {CURRENT_LEASE})",
    "deposit_movement_voids": "EXISTS (SELECT 1 FROM deposit_movements m"
    " JOIN deposits d ON d.id = m.deposit_id"
    " WHERE m.id = deposit_movement_voids.deposit_movement_id"
    f" AND d.lease_id = {CURRENT_LEASE})",
    "files": "EXISTS (SELECT 1 FROM voucher_submissions v WHERE v.file_id = files.id"
    f" AND v.lease_id = {CURRENT_LEASE})",
    "renters": "EXISTS (SELECT 1 FROM leases l WHERE l.renter_id = renters.id"
    f" AND l.id = {CURRENT_LEASE})",
    "units": "EXISTS (SELECT 1 FROM leases l WHERE l.unit_id = units.id"
    f" AND l.id = {CURRENT_LEASE})",
    "properties": "EXISTS (SELECT 1 FROM units u JOIN leases l ON l.unit_id = u.id"
    f" WHERE u.property_id = properties.id AND l.id = {CURRENT_LEASE})",
}

ADMIN_TABLES = ("accounts", "subscriptions", "subscription_payments")


def account_policy(table: str) -> str:
    column = "id" if table == "accounts" else "account_id"
    condition = f"{column} = {CURRENT_ACCOUNT}"
    return (
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;\n"
        f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;\n"
        f"CREATE POLICY account_isolation ON {table}"
        f" USING ({condition}) WITH CHECK ({condition});\n"
    )


def tenant_policy(table: str) -> str:
    if table in TENANT_VISIBLE_TABLES:
        scope: str | None = f"{CURRENT_LEASE} IS NOT NULL"
    else:
        scope = TENANT_SCOPE.get(table)
    condition = f"{OUTSIDE_TENANT_CONTEXT} OR {scope}" if scope else OUTSIDE_TENANT_CONTEXT
    return (
        f"CREATE POLICY tenant_scope ON {table} AS RESTRICTIVE"
        f" USING ({condition}) WITH CHECK ({condition});\n"
    )


def admin_policy(table: str) -> str:
    return (
        f"CREATE POLICY admin_access ON {table} TO casero_admin USING (true) WITH CHECK (true);\n"
    )


POLICIES = "".join(
    account_policy(table) + tenant_policy(table) for table in ACCOUNT_TABLES
) + "".join(admin_policy(table) for table in ADMIN_TABLES)

APPLICATION_GRANTS = """
GRANT SELECT, INSERT ON {tables} TO casero_app, casero_worker;
GRANT UPDATE ON accounts, properties, units, renters, message_templates
    TO casero_app, casero_worker;
GRANT UPDATE (end_date, ended_at, due_day, tools_enabled, tax_treatment) ON leases
    TO casero_app, casero_worker;
GRANT UPDATE (status, reject_reason, payment_id, reviewed_by, reviewed_at) ON voucher_submissions
    TO casero_app, casero_worker;
GRANT UPDATE (revoked_at, last_used_at) ON tenant_links TO casero_app, casero_worker;
GRANT UPDATE (revoked_at) ON push_subscriptions TO casero_app, casero_worker;
GRANT UPDATE (ends_at, ended_at) ON subscriptions TO casero_app, casero_worker;
GRANT UPDATE (purged_at) ON files TO casero_worker;

GRANT SELECT (id, display_name, created_at, deletion_requested_at, purged_at) ON accounts
    TO casero_admin;
GRANT SELECT, INSERT ON subscriptions, subscription_payments TO casero_admin;
GRANT UPDATE (ends_at, ended_at, founder) ON subscriptions TO casero_admin;
""".format(tables=", ".join(ACCOUNT_TABLES))


def upgrade() -> None:
    execute_script(TABLES)
    execute_script(POLICIES)
    execute_script(APPLICATION_GRANTS)


def downgrade() -> None:
    raise NotImplementedError("Migrations are forward-only")
