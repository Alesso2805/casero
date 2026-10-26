from casero.shared.infrastructure.migrations import execute_script

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_script("""
    """)


def downgrade() -> None:
    raise NotImplementedError("Migrations are forward-only")
