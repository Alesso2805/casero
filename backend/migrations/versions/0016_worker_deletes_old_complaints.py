from casero.shared.infrastructure.migrations import execute_script

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

# Complaints are kept for 2 years from filing, the Reglamento's minimum (SPEC, "Retención").
WORKER_FORGETS_COMPLAINTS = "GRANT DELETE ON complaints TO casero_worker;"


def upgrade() -> None:
    execute_script(WORKER_FORGETS_COMPLAINTS)


def downgrade() -> None:
    raise NotImplementedError("Migrations are forward-only")
