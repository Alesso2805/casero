from casero.shared.infrastructure.migrations import execute_script

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

DATA = """
INSERT INTO plans (code, name, price_month_cents, price_year_cents, max_active_leases, features)
VALUES
    ('free', 'Gratis', 0, 0, 1, '{
        "whatsapp_links": true,
        "tenant_portal": true,
        "tax_module": false,
        "tax_reminders": false,
        "receipts_pdf": false,
        "accountant_export": false,
        "data_export": true
    }'),
    ('casero', 'Casero', 1900, 19000, 10, '{
        "whatsapp_links": true,
        "tenant_portal": true,
        "tax_module": true,
        "tax_reminders": true,
        "receipts_pdf": true,
        "accountant_export": true,
        "data_export": true
    }');

INSERT INTO legal_documents (id, kind, version, published_at, url)
VALUES
    ('01a175b4-8f38-727d-a7dc-40a7a7b3647d', 'terms', '0.1', '2026-10-25', '/legal/terminos/0.1'),
    ('01a175b4-8f38-727d-a7dc-40a841bf7205', 'privacy', '0.1', '2026-10-25',
     '/legal/privacidad/0.1'),
    ('01a175b4-8f38-727d-a7dc-40a9cb61aadd', 'sensitive_consent', '0.1', '2026-10-25',
     '/legal/consentimiento-datos-sensibles/0.1');
"""


def upgrade() -> None:
    execute_script(DATA)


def downgrade() -> None:
    raise NotImplementedError("Migrations are forward-only")
