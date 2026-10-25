CRUD = frozenset({"SELECT", "INSERT", "UPDATE", "DELETE"})
SELECT = frozenset({"SELECT"})

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

TABLE_PRIVILEGES = {
    "casero_app": {
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
        "complaint_counters": frozenset({"SELECT", "INSERT", "UPDATE"}),
        "email_suppressions": frozenset({"SELECT", "INSERT"}),
    },
    "casero_worker": {
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
        "registration_invites": frozenset({"SELECT", "INSERT"}),
        "plans": SELECT,
        "tax_rule_sets": SELECT,
        "sunat_due_dates": SELECT,
        "holidays": SELECT,
        "staff_users": SELECT,
        "staff_sessions": frozenset({"SELECT", "INSERT"}),
        "staff_audit_log": frozenset({"INSERT"}),
    },
}

COLUMN_PRIVILEGES = {
    "casero_app": {
        "registration_invites": {"UPDATE": frozenset({"used_at"})},
        "waitlist_entries": {"SELECT": frozenset({"email"})},
    },
    "casero_worker": {
        "users": {"SELECT": frozenset({"id", "email", "email_verified_at", "deleted_at"})},
        "rate_limit_buckets": {"SELECT": frozenset({"window_start"})},
    },
    "casero_admin": {
        "users": {"SELECT": frozenset({"id", "email", "created_at", "email_verified_at"})},
        "complaints": {"UPDATE": frozenset({"response", "responded_at"})},
        "staff_sessions": {"UPDATE": frozenset({"revoked_at", "last_seen_at"})},
        "staff_users": {"UPDATE": frozenset({"recovery_codes_hash"})},
    },
}
