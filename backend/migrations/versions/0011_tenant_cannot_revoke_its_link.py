from casero.shared.infrastructure.migrations import execute_script

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

# The portal's one write is the link's last_used_at (D7). RLS can't compare a row with its
# previous version, so in the tenant context an updated link must still be in use: the
# portal can never revoke it (critical review of Sprints 7-9).
TENANT_KEEPS_ITS_LINK = """
CREATE POLICY tenant_keeps_link_in_use ON tenant_links AS RESTRICTIVE FOR UPDATE
    USING (true)
    WITH CHECK (
        current_setting('app.context', true) IS DISTINCT FROM 'tenant' OR revoked_at IS NULL
    );
"""


def upgrade() -> None:
    execute_script(TENANT_KEEPS_ITS_LINK)


def downgrade() -> None:
    raise NotImplementedError("Migrations are forward-only")
