from casero.shared.infrastructure.migrations import execute_script

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

SHEET = """
ALTER TABLE complaints DROP CONSTRAINT complaints_number_check;
ALTER TABLE complaints RENAME COLUMN document TO document_number;
ALTER TABLE complaints
    ADD CONSTRAINT complaints_number_check CHECK (number ~ '^[0-9]{9}-[0-9]{4}$'),
    ADD COLUMN document_type text NOT NULL CHECK (document_type IN ('dni', 'ce', 'passport')),
    ADD COLUMN address text,
    ALTER COLUMN email DROP NOT NULL,
    ADD COLUMN guardian_name text,
    ADD COLUMN guardian_address text,
    ADD COLUMN guardian_phone text,
    ADD COLUMN guardian_email text,
    ADD COLUMN item_kind text NOT NULL CHECK (item_kind IN ('product', 'service')),
    ADD COLUMN claimed_amount_cents bigint CHECK (claimed_amount_cents >= 0),
    ADD COLUMN item_description text,
    ALTER COLUMN request DROP NOT NULL,
    ADD COLUMN response_channel text NOT NULL CHECK (response_channel IN ('email', 'letter')),
    ADD CONSTRAINT complaints_response_contact_check CHECK (
        (response_channel = 'email' AND email IS NOT NULL)
        OR (response_channel = 'letter' AND address IS NOT NULL)
    ),
    ADD CONSTRAINT complaints_guardian_check CHECK (
        guardian_name IS NOT NULL
        OR num_nulls(guardian_address, guardian_phone, guardian_email) = 3
    );
"""


def upgrade() -> None:
    execute_script(SHEET)


def downgrade() -> None:
    raise NotImplementedError("Migrations are forward-only")
