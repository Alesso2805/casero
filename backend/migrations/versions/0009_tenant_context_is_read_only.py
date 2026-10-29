from casero.shared.infrastructure.migrations import execute_script

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

# The tenant portal only reads: a bug in one of its endpoints must not be able to change the
# landlord's account or ledger (critical review of Sprints 4-6, D7). It keeps one write, the
# link's last_used_at. Vouchers and their files will be allowed with CS-19 (review I5).
TENANT_READ_ONLY = """
DO $$
DECLARE
    outside_tenant constant text :=
        'current_setting(''app.context'', true) IS DISTINCT FROM ''tenant''';
    account_table text;
BEGIN
    FOR account_table IN
        SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relrowsecurity
    LOOP
        EXECUTE format(
            'CREATE POLICY tenant_no_insert ON %I AS RESTRICTIVE FOR INSERT WITH CHECK (%s)',
            account_table, outside_tenant);
        EXECUTE format(
            'CREATE POLICY tenant_no_delete ON %I AS RESTRICTIVE FOR DELETE USING (%s)',
            account_table, outside_tenant);
        IF account_table <> 'tenant_links' THEN
            EXECUTE format(
                'CREATE POLICY tenant_no_update ON %I AS RESTRICTIVE FOR UPDATE USING (%s)',
                account_table, outside_tenant);
        END IF;
    END LOOP;
END
$$;
"""


def upgrade() -> None:
    execute_script(TENANT_READ_ONLY)


def downgrade() -> None:
    raise NotImplementedError("Migrations are forward-only")
