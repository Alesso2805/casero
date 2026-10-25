# ADR-0007: Personal data: encryption, hashing, retention and two-phase purge

- Status: Accepted
- Date: 2026-10-25
- Story: CS-01

## Context

Casero stores landlords' rental income, which Peru's Law 29733 treats as sensitive data, and third-party data about tenants: names, phones and identity documents. A leak or an incomplete deletion would break the law and the product's promise. Peru's regulation (D.S. 016-2024-JUS) also requires notifying incidents and honoring deletion.

## Decision

### Minimal data

The tenant document is required only for leases that enter the tax module, because the Formulario 1683 needs it.

### Encryption at rest

- Every `*_enc` column uses AES-256-GCM (cryptography's `AESGCM`). The columns are `renters.doc_enc`, `accounts.deletion_contact_enc` and `staff_users.totp_secret_enc`.
- Each value is stored as an envelope: `v1:<key_id>:<nonce>:<ciphertext>`.
  - The nonce is 96 random bits.
  - The nonce and the ciphertext (which includes the tag) are base64url.
  - The associated data binds the value to its table, column and account, so a ciphertext cannot be moved to another row.
- Keys live outside the database:
  - The environment holds the set of keys by id and the id of the active key.
  - The source of truth is Bitwarden.
- Rotation means adding a key, making it active and re-encrypting the columns with a one-off job. Old keys are removed once nothing references them.

### Document HMAC

- `renters.doc_hmac = HMAC-SHA256(DOC_HMAC_KEY, "<doc_type>:<normalized_number>")`.
- `doc_type` is one of `dni`, `ce`, `passport` and `ruc`.
- To normalize the number: apply Unicode NFKC, trim, remove spaces, hyphens and dots, and uppercase. Per-type validation (DNI of 8 digits, RUC of 11 digits with check digit, and so on) is part of CS-09.
- The HMAC groups declarations and identifies SUNAT payments in append-only tables (`tax_payments`, `reminder_logs`). The key is therefore permanent and is documented as not rotatable.
- If the key is compromised, the response is a migration with its own ADR.
- Because DNI numbers are an 8-digit space, a leaked key would allow a dictionary attack. The key is protected like the encryption keys.
- `doc_last4` is kept for display. The full number is decrypted only in the 1683 card.

### Logs and error tracking

- A structlog processor drops known personal fields. Logs never include request bodies, query strings, cookies or `X-Tenant-Token`.
- Error tracking uses `before_send` scrubbing plus the provider's server-side scrubbing.
- Caddy does not log `/i` or query strings.
- A test verifies that a document number does not appear in plain text in the database, the logs or the error-tracking payloads.

### Retention

Retention follows the table in SPEC.md:

- Account data is kept while the account exists.
- Rejected vouchers are kept for 90 days.
- Old object versions are kept for 30 days.
- `deletion_contact_enc` is kept only during the 30-day wait.
- Subscription payments are kept as long as the accountant requires.
- Complaints are kept for the legal period.
- Waitlist entries are kept until registration or for 12 months.
- Backups are kept for 30 days.

Voucher files are unique by `(account_id, sha256)` only among rows that are not purged, so uploading a purged file again creates a new row.

### Account deletion

1. **Request:**
   - The original email is encrypted into `deletion_contact_enc`.
   - `users.email` becomes `deleted+<id>@invalid`.
   - Access is blocked.
   - The purge is scheduled 30 days later.
2. **Cancel:** the email link calls `app_cancel_deletion(p_token_hash, p_now)` (ADR-0002). In the same transaction, the application decrypts the returned envelope and restores the email.
3. **Purge, phase 1:** the worker queues every object of the account in `pending_object_deletions` and deletes each one with all its versions.
4. **Purge, phase 2:** when the queue is empty, the worker decrypts `deletion_contact_enc` and calls `purge_account(p_account_id, p_today, p_email)`, which:
   - checks that the scheduled date has passed;
   - deletes rows in dependency order: account data, `job_runs` and `pending_object_deletions` of the account, `registration_invites` for that email, and the user with their sessions and email tokens;
   - keeps only the anonymized `accounts` row, marked as purged, and its `subscription_payments`.

Backups are encrypted, locked for 30 days and expire after 30 days, so purged data disappears from them within that window. The privacy policy says so.

## Consequences

- A database dump alone does not reveal documents, deletion contacts or TOTP secrets.
- The document HMAC key is a long-lived secret. Losing it breaks grouping of past declarations, so it must be backed up as carefully as the encryption keys.
- Deletion is not immediate in backups. This is disclosed rather than hidden.

## Enforcement

- A test that no row with the account id, the user, or an invite with the email remains after a purge.
- A test that the document does not appear in plain text in the database, logs or error tracking.
- Envelope round-trip tests, including a rejected ciphertext with mismatched associated data.
