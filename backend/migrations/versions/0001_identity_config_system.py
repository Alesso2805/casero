from casero.shared.infrastructure.migrations import execute_script

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

TABLES = """
CREATE TABLE users (
    id uuid PRIMARY KEY,
    email text NOT NULL,
    password_hash text NOT NULL,
    email_verified_at timestamptz,
    created_at timestamptz NOT NULL,
    deleted_at timestamptz
);
CREATE UNIQUE INDEX users_email_key ON users (lower(email));

CREATE TABLE sessions (
    id uuid PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES users (id),
    token_hash bytea NOT NULL UNIQUE,
    created_at timestamptz NOT NULL,
    last_seen_at timestamptz NOT NULL,
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz
);

CREATE TABLE email_tokens (
    id uuid PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES users (id),
    purpose text NOT NULL CHECK (purpose IN ('verify_email', 'reset_password', 'cancel_deletion')),
    token_hash bytea NOT NULL UNIQUE,
    expires_at timestamptz NOT NULL,
    used_at timestamptz
);

CREATE TABLE staff_users (
    id uuid PRIMARY KEY,
    email text NOT NULL,
    password_hash text NOT NULL,
    totp_secret_enc text NOT NULL,
    recovery_codes_hash text[] NOT NULL,
    created_at timestamptz NOT NULL,
    disabled_at timestamptz
);
CREATE UNIQUE INDEX staff_users_email_key ON staff_users (lower(email));

CREATE TABLE staff_sessions (
    id uuid PRIMARY KEY,
    staff_user_id uuid NOT NULL REFERENCES staff_users (id),
    token_hash bytea NOT NULL UNIQUE,
    created_at timestamptz NOT NULL,
    last_seen_at timestamptz NOT NULL,
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz
);

CREATE TABLE staff_audit_log (
    id uuid PRIMARY KEY,
    staff_user_id uuid REFERENCES staff_users (id),
    actor text NOT NULL CHECK (actor IN ('panel', 'cli')),
    action text NOT NULL,
    entity text NOT NULL,
    entity_id uuid,
    at timestamptz NOT NULL,
    CHECK (staff_user_id IS NOT NULL OR actor = 'cli')
);

CREATE TABLE registration_invites (
    id uuid PRIMARY KEY,
    email text NOT NULL,
    token_hash bytea NOT NULL UNIQUE,
    created_by_staff_id uuid REFERENCES staff_users (id),
    expires_at timestamptz NOT NULL,
    used_at timestamptz
);

CREATE TABLE account_members (
    account_id uuid NOT NULL,
    user_id uuid NOT NULL REFERENCES users (id),
    role text NOT NULL CHECK (role = 'owner'),
    PRIMARY KEY (account_id, user_id),
    UNIQUE (account_id),
    UNIQUE (user_id)
);

CREATE TABLE legal_documents (
    id uuid PRIMARY KEY,
    kind text NOT NULL CHECK (kind IN ('terms', 'privacy', 'sensitive_consent')),
    version text NOT NULL,
    published_at date NOT NULL,
    url text NOT NULL,
    UNIQUE (kind, version)
);

CREATE TABLE plans (
    code text PRIMARY KEY CHECK (code IN ('free', 'casero')),
    name text NOT NULL,
    price_month_cents bigint NOT NULL CHECK (price_month_cents >= 0),
    price_year_cents bigint NOT NULL CHECK (price_year_cents >= 0),
    max_active_leases integer NOT NULL CHECK (max_active_leases > 0),
    features jsonb NOT NULL
);

CREATE TABLE tax_rule_sets (
    year integer PRIMARY KEY,
    rate_bp integer NOT NULL CHECK (rate_bp > 0),
    deduction_bp integer NOT NULL CHECK (deduction_bp >= 0),
    rounding text NOT NULL CHECK (rounding IN ('half_up_sol')),
    cash_threshold_cents bigint NOT NULL CHECK (cash_threshold_cents > 0),
    min_rent_bp integer NOT NULL CHECK (min_rent_bp > 0),
    uit_cents bigint NOT NULL CHECK (uit_cents > 0),
    source_url text NOT NULL
);

CREATE TABLE sunat_due_dates (
    year integer NOT NULL,
    period text NOT NULL CHECK (period ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
    ruc_group text NOT NULL CHECK (ruc_group IN ('0', '1', '2-3', '4-5', '6-7', '8-9', 'bc')),
    due_date date NOT NULL,
    source_url text NOT NULL,
    PRIMARY KEY (year, period, ruc_group),
    CHECK (left(period, 4)::integer = year)
);

CREATE TABLE holidays (
    date date PRIMARY KEY,
    name text NOT NULL
);

CREATE TABLE complaints (
    id uuid PRIMARY KEY,
    number text NOT NULL UNIQUE CHECK (number ~ '^[0-9]{4}-[0-9]{6}$'),
    created_at timestamptz NOT NULL,
    full_name text NOT NULL,
    document text NOT NULL,
    email text NOT NULL,
    phone text,
    kind text NOT NULL CHECK (kind IN ('claim', 'complaint')),
    detail text NOT NULL,
    request text NOT NULL,
    response text,
    responded_at timestamptz,
    due_at date NOT NULL,
    CHECK ((response IS NULL) = (responded_at IS NULL))
);

CREATE TABLE complaint_counters (
    year integer PRIMARY KEY,
    last_number integer NOT NULL CHECK (last_number >= 0)
);

CREATE TABLE waitlist_entries (
    id uuid PRIMARY KEY,
    email text NOT NULL,
    source text NOT NULL,
    consented_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL
);
CREATE UNIQUE INDEX waitlist_entries_email_key ON waitlist_entries (lower(email));

CREATE TABLE email_suppressions (
    email_hash bytea NOT NULL,
    email_kind text CHECK (email_kind IN ('daily_digest', 'tax_reminders')),
    reason text NOT NULL CHECK (reason IN ('bounce', 'complaint', 'unsubscribe')),
    created_at timestamptz NOT NULL,
    UNIQUE NULLS NOT DISTINCT (email_hash, email_kind),
    CHECK ((reason = 'unsubscribe') = (email_kind IS NOT NULL))
);

CREATE UNLOGGED TABLE rate_limit_buckets (
    key_hash bytea NOT NULL,
    window_start timestamptz NOT NULL,
    count integer NOT NULL CHECK (count > 0),
    PRIMARY KEY (key_hash, window_start)
);

CREATE TABLE job_runs (
    job text NOT NULL,
    run_key text NOT NULL,
    account_id uuid,
    status text NOT NULL CHECK (status IN ('running', 'done', 'failed')),
    attempts integer NOT NULL CHECK (attempts > 0),
    started_at timestamptz NOT NULL,
    finished_at timestamptz,
    error_code text,
    UNIQUE NULLS NOT DISTINCT (job, run_key, account_id)
);

CREATE TABLE pending_object_deletions (
    storage_key text PRIMARY KEY,
    account_id uuid NOT NULL,
    requested_at timestamptz NOT NULL,
    attempts integer NOT NULL CHECK (attempts >= 0),
    done_at timestamptz
);
"""

GRANTS = """
GRANT SELECT, INSERT, UPDATE, DELETE
    ON users, sessions, email_tokens, account_members, rate_limit_buckets TO casero_app;
GRANT SELECT ON registration_invites TO casero_app;
GRANT UPDATE (used_at) ON registration_invites TO casero_app;
GRANT SELECT ON plans, tax_rule_sets, sunat_due_dates, holidays, legal_documents TO casero_app;
GRANT INSERT ON complaints TO casero_app;
GRANT INSERT, DELETE ON waitlist_entries TO casero_app;
GRANT SELECT (email) ON waitlist_entries TO casero_app;
GRANT SELECT, INSERT, UPDATE ON complaint_counters TO casero_app;
GRANT SELECT, INSERT ON email_suppressions TO casero_app;

GRANT SELECT (id, email, email_verified_at, deleted_at) ON users TO casero_worker;
GRANT SELECT
    ON account_members, plans, tax_rule_sets, sunat_due_dates, complaints, holidays,
       waitlist_entries
    TO casero_worker;
GRANT DELETE ON waitlist_entries, rate_limit_buckets TO casero_worker;
GRANT SELECT (window_start) ON rate_limit_buckets TO casero_worker;
GRANT SELECT, INSERT, UPDATE, DELETE
    ON job_runs, pending_object_deletions, email_suppressions TO casero_worker;

GRANT SELECT
    ON account_members, complaints, job_runs, waitlist_entries, registration_invites, plans,
       tax_rule_sets, sunat_due_dates, holidays, staff_users, staff_sessions
    TO casero_admin;
GRANT SELECT (id, email, created_at, email_verified_at) ON users TO casero_admin;
GRANT INSERT ON registration_invites, staff_sessions, staff_audit_log TO casero_admin;
GRANT UPDATE (response, responded_at) ON complaints TO casero_admin;
GRANT UPDATE (revoked_at, last_seen_at) ON staff_sessions TO casero_admin;
GRANT UPDATE (recovery_codes_hash) ON staff_users TO casero_admin;
"""


def upgrade() -> None:
    execute_script(TABLES)
    execute_script(GRANTS)


def downgrade() -> None:
    raise NotImplementedError("Migrations are forward-only")
