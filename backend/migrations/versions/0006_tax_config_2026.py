from alembic import op

from casero.tax.infrastructure.tax_config import read_year, seed_dir, statements

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    for statement, rows in statements(read_year(seed_dir() / "2026.yaml")):
        bind.execute(statement, rows)


def downgrade() -> None:
    raise NotImplementedError("Migrations are forward-only")
