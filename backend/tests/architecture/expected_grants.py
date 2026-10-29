CRUD = frozenset({"SELECT", "INSERT", "UPDATE", "DELETE"})
SELECT = frozenset({"SELECT"})
READ_AND_INSERT = frozenset({"SELECT", "INSERT"})
READ_INSERT_UPDATE = frozenset({"SELECT", "INSERT", "UPDATE"})

TABLES_WITHOUT_RLS = frozenset(
    {
        "users",
        "sessions",
        "email_tokens",
        "registration_invites",
        "account_members",
        "legal_documents",
        "staff_users",
        "staff_sessions",
        "staff_audit_log",
        "plans",
        "tax_rule_sets",
        "sunat_due_dates",
        "holidays",
        "complaints",
        "complaint_counters",
        "waitlist_entries",
        "email_suppressions",
        "rate_limit_buckets",
        "job_runs",
        "pending_object_deletions",
        "alembic_version",
    }
)

ACCOUNT_TABLES = frozenset(
    {
        "accounts",
        "legal_acceptances",
        "legal_withdrawals",
        "subscriptions",
        "subscription_payments",
        "push_subscriptions",
        "properties",
        "units",
        "renters",
        "leases",
        "lease_rent_changes",
        "charges",
        "charge_voids",
        "payments",
        "payment_voids",
        "deposits",
        "deposit_voids",
        "deposit_movements",
        "deposit_movement_voids",
        "voucher_submissions",
        "tenant_links",
        "files",
        "message_templates",
        "reminder_logs",
        "tax_payments",
        "tax_payment_voids",
        "audit_log",
    }
)

EDITABLE_ACCOUNT_TABLES = frozenset(
    {"accounts", "properties", "units", "renters", "message_templates"}
)

ACCOUNT_TABLE_PRIVILEGES = {
    table: READ_INSERT_UPDATE if table in EDITABLE_ACCOUNT_TABLES else READ_AND_INSERT
    for table in ACCOUNT_TABLES
}

ACCOUNT_COLUMN_UPDATES = {
    "leases": {
        "UPDATE": frozenset({"end_date", "ended_at", "due_day", "tools_enabled", "tax_treatment"})
    },
    "voucher_submissions": {
        "UPDATE": frozenset({"status", "reject_reason", "payment_id", "reviewed_by", "reviewed_at"})
    },
    "tenant_links": {"UPDATE": frozenset({"revoked_at", "last_used_at"})},
    "push_subscriptions": {"UPDATE": frozenset({"revoked_at"})},
    "subscriptions": {"UPDATE": frozenset({"ends_at", "ended_at"})},
}

TABLE_PRIVILEGES = {
    "casero_app": {
        **ACCOUNT_TABLE_PRIVILEGES,
        "users": CRUD,
        "sessions": CRUD,
        "email_tokens": CRUD,
        "account_members": CRUD,
        "rate_limit_buckets": CRUD,
        "registration_invites": SELECT,
        "plans": SELECT,
        "tax_rule_sets": SELECT,
        "sunat_due_dates": SELECT,
        "holidays": SELECT,
        "legal_documents": SELECT,
        "complaints": frozenset({"INSERT"}),
        "waitlist_entries": frozenset({"INSERT", "DELETE"}),
        "complaint_counters": READ_INSERT_UPDATE,
        "email_suppressions": frozenset({"SELECT", "INSERT", "DELETE"}),
    },
    "casero_worker": {
        **ACCOUNT_TABLE_PRIVILEGES,
        "account_members": SELECT,
        "plans": SELECT,
        "tax_rule_sets": SELECT,
        "sunat_due_dates": SELECT,
        "complaints": SELECT,
        "holidays": SELECT,
        "waitlist_entries": frozenset({"SELECT", "DELETE"}),
        "rate_limit_buckets": frozenset({"DELETE"}),
        "job_runs": CRUD,
        "pending_object_deletions": CRUD,
        "email_suppressions": CRUD,
    },
    "casero_admin": {
        "account_members": SELECT,
        "complaints": SELECT,
        "job_runs": SELECT,
        "waitlist_entries": SELECT,
        "registration_invites": READ_AND_INSERT,
        "plans": SELECT,
        "tax_rule_sets": SELECT,
        "sunat_due_dates": SELECT,
        "holidays": SELECT,
        "staff_users": SELECT,
        "staff_sessions": READ_AND_INSERT,
        "staff_audit_log": frozenset({"INSERT"}),
        "subscriptions": READ_AND_INSERT,
        "subscription_payments": READ_AND_INSERT,
    },
}

COLUMN_PRIVILEGES = {
    "casero_app": {
        **ACCOUNT_COLUMN_UPDATES,
        "registration_invites": {"UPDATE": frozenset({"used_at"})},
        "waitlist_entries": {"SELECT": frozenset({"email"})},
    },
    "casero_worker": {
        **ACCOUNT_COLUMN_UPDATES,
        "files": {"UPDATE": frozenset({"purged_at"})},
        "users": {"SELECT": frozenset({"id", "email", "email_verified_at", "deleted_at"})},
        "rate_limit_buckets": {"SELECT": frozenset({"window_start"})},
    },
    "casero_admin": {
        "accounts": {
            "SELECT": frozenset(
                {"id", "display_name", "created_at", "deletion_requested_at", "purged_at"}
            )
        },
        "subscriptions": {"UPDATE": frozenset({"ends_at", "ended_at", "founder"})},
        "users": {"SELECT": frozenset({"id", "email", "created_at", "email_verified_at"})},
        "complaints": {"UPDATE": frozenset({"response", "responded_at"})},
        "staff_sessions": {"UPDATE": frozenset({"revoked_at", "last_seen_at"})},
        "staff_users": {"UPDATE": frozenset({"recovery_codes_hash"})},
    },
}

FUNCTION_EXECUTORS = {
    "app_resolve_tenant_token": frozenset({"casero_app"}),
    "app_cancel_deletion": frozenset({"casero_app"}),
    "app_list_account_ids": frozenset({"casero_worker"}),
    "purge_account": frozenset({"casero_worker"}),
}
