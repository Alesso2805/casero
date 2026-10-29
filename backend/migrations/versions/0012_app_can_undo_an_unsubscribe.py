from casero.shared.infrastructure.migrations import execute_script

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

# Mis datos undoes the user's own unsubscribe from the SUNAT reminders; the application deletes
# only rows with reason 'unsubscribe' for that address and kind, never bounces or complaints.
APP_UNDOES_UNSUBSCRIBES = "GRANT DELETE ON email_suppressions TO casero_app;"


def upgrade() -> None:
    execute_script(APP_UNDOES_UNSUBSCRIBES)


def downgrade() -> None:
    raise NotImplementedError("Migrations are forward-only")
