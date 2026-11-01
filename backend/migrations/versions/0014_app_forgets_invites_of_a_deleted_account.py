from casero.shared.infrastructure.migrations import execute_script

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

# The API has the keys to the contact, and the worker has none, so the invitations of an email
# go when its owner asks for the deletion instead of at the purge (owner's decision, CS-25).
APP_FORGETS_INVITES = "GRANT DELETE ON registration_invites TO casero_app;"


def upgrade() -> None:
    execute_script(APP_FORGETS_INVITES)


def downgrade() -> None:
    raise NotImplementedError("Migrations are forward-only")
