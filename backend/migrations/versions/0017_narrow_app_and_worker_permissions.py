from casero.shared.infrastructure.migrations import execute_script

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

# Each role keeps what it uses (owner's decision, CS-23). The worker never writes accounts or
# subscriptions, and only the panel records subscription payments. account_isolation applied to
# PUBLIC, so casero_admin with app.account_id set saw rows of any table it could read; now it
# sees only what its own policies allow, as ADR-0002 promises.
NARROWED = """
REVOKE UPDATE ON accounts FROM casero_app, casero_worker;
GRANT UPDATE (
    display_name, taxpayer_kind, ruc, ruc_group, daily_digest,
    deletion_requested_at, deletion_scheduled_for, deletion_contact_enc
) ON accounts TO casero_app;
REVOKE INSERT ON subscription_payments FROM casero_app, casero_worker;
REVOKE INSERT ON subscriptions FROM casero_worker;

DO $$
DECLARE
    account_table text;
BEGIN
    FOR account_table IN
        SELECT tablename FROM pg_policies
        WHERE schemaname = 'public' AND policyname = 'account_isolation'
    LOOP
        EXECUTE format(
            'ALTER POLICY account_isolation ON %I TO casero_app, casero_worker', account_table);
    END LOOP;
END
$$;
"""


def upgrade() -> None:
    execute_script(NARROWED)


def downgrade() -> None:
    raise NotImplementedError("Migrations are forward-only")
