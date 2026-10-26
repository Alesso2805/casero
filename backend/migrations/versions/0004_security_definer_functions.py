from casero.shared.infrastructure.migrations import execute_script

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

FUNCTIONS = """
CREATE FUNCTION app_resolve_tenant_token(p_hash bytea, p_today date)
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
      AND (l.ended_at IS NULL OR l.ended_at + 90 >= p_today);
END;
$$;

CREATE FUNCTION app_list_account_ids(p_purpose text, p_today date)
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

CREATE FUNCTION app_cancel_deletion(p_token_hash bytea, p_now timestamptz)
RETURNS TABLE (account_id uuid, user_id uuid, deletion_contact_enc text)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_token_id uuid;
    v_user_id uuid;
    v_account_id uuid;
    v_contact text;
BEGIN
    IF p_token_hash IS NULL OR octet_length(p_token_hash) <> 32 OR p_now IS NULL THEN
        RAISE EXCEPTION 'invalid arguments' USING ERRCODE = '22023';
    END IF;

    SELECT t.id, t.user_id INTO v_token_id, v_user_id
    FROM email_tokens t
    WHERE t.token_hash = p_token_hash
      AND t.purpose = 'cancel_deletion'
      AND t.used_at IS NULL
      AND t.expires_at > p_now
    FOR UPDATE;
    IF NOT FOUND THEN
        RETURN;
    END IF;

    UPDATE email_tokens SET used_at = p_now WHERE id = v_token_id;

    SELECT a.id, a.deletion_contact_enc INTO v_account_id, v_contact
    FROM accounts a
    JOIN account_members m ON m.account_id = a.id
    WHERE m.user_id = v_user_id
      AND a.deletion_requested_at IS NOT NULL
      AND a.purged_at IS NULL
    FOR UPDATE OF a;
    IF NOT FOUND THEN
        RETURN;
    END IF;

    UPDATE accounts
    SET deletion_requested_at = NULL, deletion_scheduled_for = NULL, deletion_contact_enc = NULL
    WHERE id = v_account_id;

    RETURN QUERY SELECT v_account_id, v_user_id, v_contact;
END;
$$;

CREATE FUNCTION purge_account(p_account_id uuid, p_today date, p_email text)
RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_user_id uuid;
BEGIN
    IF p_account_id IS NULL OR p_today IS NULL OR p_email IS NULL THEN
        RAISE EXCEPTION 'invalid arguments' USING ERRCODE = '22023';
    END IF;
    PERFORM set_config('app.account_id', p_account_id::text, true);

    PERFORM 1 FROM accounts a
    WHERE a.id = p_account_id AND a.purged_at IS NULL AND a.deletion_scheduled_for <= p_today
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'account is not due for purge' USING ERRCODE = '55000';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pending_object_deletions d
        WHERE d.account_id = p_account_id AND d.done_at IS NULL
    ) THEN
        RAISE EXCEPTION 'storage objects are still pending deletion' USING ERRCODE = '55000';
    END IF;

    SELECT m.user_id INTO v_user_id FROM account_members m WHERE m.account_id = p_account_id;

    DELETE FROM tax_payment_voids WHERE account_id = p_account_id;
    DELETE FROM tax_payments WHERE account_id = p_account_id;
    DELETE FROM reminder_logs WHERE account_id = p_account_id;
    DELETE FROM message_templates WHERE account_id = p_account_id;
    DELETE FROM tenant_links WHERE account_id = p_account_id;
    DELETE FROM voucher_submissions WHERE account_id = p_account_id;
    DELETE FROM deposit_movement_voids WHERE account_id = p_account_id;
    DELETE FROM deposit_movements WHERE account_id = p_account_id;
    DELETE FROM deposit_voids WHERE account_id = p_account_id;
    DELETE FROM payment_voids WHERE account_id = p_account_id;
    DELETE FROM payments WHERE account_id = p_account_id;
    DELETE FROM charge_voids WHERE account_id = p_account_id;
    DELETE FROM charges WHERE account_id = p_account_id;
    DELETE FROM deposits WHERE account_id = p_account_id;
    DELETE FROM lease_rent_changes WHERE account_id = p_account_id;
    DELETE FROM files WHERE account_id = p_account_id;
    DELETE FROM leases WHERE account_id = p_account_id;
    DELETE FROM renters WHERE account_id = p_account_id;
    DELETE FROM units WHERE account_id = p_account_id;
    DELETE FROM properties WHERE account_id = p_account_id;
    DELETE FROM push_subscriptions WHERE account_id = p_account_id;
    DELETE FROM subscriptions WHERE account_id = p_account_id;
    DELETE FROM legal_withdrawals WHERE account_id = p_account_id;
    DELETE FROM legal_acceptances WHERE account_id = p_account_id;
    DELETE FROM audit_log WHERE account_id = p_account_id;
    DELETE FROM account_members WHERE account_id = p_account_id;
    DELETE FROM job_runs WHERE account_id = p_account_id;
    DELETE FROM pending_object_deletions WHERE account_id = p_account_id;
    DELETE FROM registration_invites WHERE lower(email) = lower(p_email);
    IF v_user_id IS NOT NULL THEN
        DELETE FROM sessions WHERE user_id = v_user_id;
        DELETE FROM email_tokens WHERE user_id = v_user_id;
        DELETE FROM users WHERE id = v_user_id;
    END IF;

    UPDATE accounts
    SET display_name = NULL, ruc = NULL, ruc_group = NULL, daily_digest = false,
        deletion_contact_enc = NULL, purged_at = p_today
    WHERE id = p_account_id;
END;
$$;

REVOKE ALL ON FUNCTION app_resolve_tenant_token(bytea, date) FROM PUBLIC;
REVOKE ALL ON FUNCTION app_list_account_ids(text, date) FROM PUBLIC;
REVOKE ALL ON FUNCTION app_cancel_deletion(bytea, timestamptz) FROM PUBLIC;
REVOKE ALL ON FUNCTION purge_account(uuid, date, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app_resolve_tenant_token(bytea, date) TO casero_app;
GRANT EXECUTE ON FUNCTION app_cancel_deletion(bytea, timestamptz) TO casero_app;
GRANT EXECUTE ON FUNCTION app_list_account_ids(text, date) TO casero_worker;
GRANT EXECUTE ON FUNCTION purge_account(uuid, date, text) TO casero_worker;
"""


def upgrade() -> None:
    execute_script(FUNCTIONS)


def downgrade() -> None:
    raise NotImplementedError("Migrations are forward-only")
