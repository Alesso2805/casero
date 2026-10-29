from casero.shared.infrastructure.migrations import execute_script

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

# A unique index also counts voided rows, so a wrong prior debt could never be entered again.
# "One valid prior debt per lease and era" is checked under the lease lock instead (CS-31).
REENTERABLE_PRIOR_DEBT = """
DROP INDEX charges_one_opening_balance_per_era;
"""


def upgrade() -> None:
    execute_script(REENTERABLE_PRIOR_DEBT)


def downgrade() -> None:
    raise NotImplementedError("Migrations are forward-only")
