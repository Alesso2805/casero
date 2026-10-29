from casero.shared.infrastructure.migrations import execute_script

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

# The base Casero showed when the payment was registered, so a later change in what was
# collected can be told as "Cobraste S/ X más" (SPEC). No rows exist before CS-34.
DECLARED_BASE = """
ALTER TABLE tax_payments ADD COLUMN base_cents bigint NOT NULL CHECK (base_cents >= 0);
"""


def upgrade() -> None:
    execute_script(DECLARED_BASE)


def downgrade() -> None:
    raise NotImplementedError("Migrations are forward-only")
