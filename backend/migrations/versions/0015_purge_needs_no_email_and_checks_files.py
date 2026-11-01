from casero.shared.infrastructure.migrations import execute_script

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

# The invitations go when the deletion is requested, because the worker holds no keys to read
# the contact (owner's decision, CS-25). The purge also refuses a file that was never queued,
# which would leave its object orphaned in the bucket.
FUNCTIONS = """
DROP FUNCTION purge_account(uuid, date, text);

CREATE FUNCTION purge_account(p_account_id uuid, p_today date)
RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_user_id uuid;
BEGIN
    IF p_account_id IS NULL OR p_today IS NULL THEN
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
    ) OR EXISTS (
        SELECT 1 FROM files f
        WHERE f.account_id = p_account_id AND f.purged_at IS NULL
          AND NOT EXISTS (
              SELECT 1 FROM pending_object_deletions d
              WHERE d.storage_key = f.storage_key AND d.done_at IS NOT NULL
          )
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

REVOKE ALL ON FUNCTION purge_account(uuid, date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION purge_account(uuid, date) TO casero_worker;
"""


def upgrade() -> None:
    execute_script(FUNCTIONS)


def downgrade() -> None:
    raise NotImplementedError("Migrations are forward-only")
