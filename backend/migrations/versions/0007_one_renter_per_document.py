from casero.shared.infrastructure.migrations import execute_script

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

# One tenant per document and account: declarations group by doc_hmac (ADR-0007).
UNIQUE_DOCUMENT = """
CREATE UNIQUE INDEX renters_one_per_document ON renters (account_id, doc_hmac)
    WHERE doc_hmac IS NOT NULL;
"""


def upgrade() -> None:
    execute_script(UNIQUE_DOCUMENT)


def downgrade() -> None:
    raise NotImplementedError("Migrations are forward-only")
