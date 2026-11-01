from casero.shared.infrastructure.migrations import execute_script

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

# A withdrawn sensitive-data consent blocks the account (SPEC, "Datos personales"): no job treats
# its income data and its tenant link stops answering until the consent is given again. The
# predicate is accounts.domain.legal.latest_consent in SQL: a tie counts as withdrawn. It is
# repeated because AR-19 closes the list of functions.
FUNCTIONS = """
CREATE OR REPLACE FUNCTION app_resolve_tenant_token(p_hash bytea, p_today date)
RETURNS TABLE (account_id uuid, lease_id uuid)
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF p_hash IS NULL OR octet_length(p_hash) <> 32 OR p_today IS NULL THEN
        RAISE EXCEPTION 'invalid arguments' USING ERRCODE = '22023';
    END IF;
    RETURN QUERY
    SELECT t.account_id, t.lease_id
    FROM tenant_links t
    JOIN leases l ON l.account_id = t.account_id AND l.id = t.lease_id
    JOIN accounts a ON a.id = t.account_id
    WHERE t.token_hash = p_hash
      AND t.revoked_at IS NULL
      AND a.deletion_requested_at IS NULL
      AND a.purged_at IS NULL
      AND (l.ended_at IS NULL OR l.ended_at + 90 >= p_today)
      AND NOT EXISTS (
          SELECT 1 FROM legal_withdrawals w
          JOIN legal_documents wd ON wd.id = w.document_id
          WHERE w.account_id = a.id AND wd.kind = 'sensitive_consent'
            AND NOT EXISTS (
                SELECT 1 FROM legal_acceptances c
                JOIN legal_documents cd ON cd.id = c.document_id
                WHERE c.account_id = a.id AND cd.kind = 'sensitive_consent'
                  AND c.accepted_at > w.withdrawn_at
            )
      );
END;
$$;

CREATE OR REPLACE FUNCTION app_list_account_ids(p_purpose text, p_today date)
RETURNS SETOF uuid
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF p_today IS NULL THEN
        RAISE EXCEPTION 'invalid arguments' USING ERRCODE = '22023';
    END IF;
    IF p_purpose = 'jobs' THEN
        RETURN QUERY
        SELECT a.id FROM accounts a
        WHERE a.purged_at IS NULL AND a.deletion_requested_at IS NULL
          AND NOT EXISTS (
              SELECT 1 FROM legal_withdrawals w
              JOIN legal_documents wd ON wd.id = w.document_id
              WHERE w.account_id = a.id AND wd.kind = 'sensitive_consent'
                AND NOT EXISTS (
                    SELECT 1 FROM legal_acceptances c
                    JOIN legal_documents cd ON cd.id = c.document_id
                    WHERE c.account_id = a.id AND cd.kind = 'sensitive_consent'
                      AND c.accepted_at > w.withdrawn_at
                )
          )
        ORDER BY a.id;
    ELSIF p_purpose = 'purge' THEN
        RETURN QUERY
        SELECT a.id FROM accounts a
        WHERE a.purged_at IS NULL AND a.deletion_scheduled_for <= p_today
        ORDER BY a.id;
    ELSE
        RAISE EXCEPTION 'unknown purpose' USING ERRCODE = '22023';
    END IF;
END;
$$;
"""


def upgrade() -> None:
    execute_script(FUNCTIONS)


def downgrade() -> None:
    raise NotImplementedError("Migrations are forward-only")
