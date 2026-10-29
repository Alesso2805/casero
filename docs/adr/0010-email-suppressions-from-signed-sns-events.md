# ADR-0010: Email suppressions fed by signed SNS events, stored as a keyed hash

- Status: Accepted
- Date: 2026-10-26
- Story: CS-04

## Context

SES reports bounces and complaints through SNS. SPEC.md asks for:

- a webhook that verifies each message's signature and feeds `email_suppressions`;
- a permanent bounce or a complaint stops every email to that address, including transactional ones;
- an unsubscribe stops only that kind of scheduled email. The user can undo it from Mis datos (review of Sprints 7-9, I22): `casero_app` deletes only rows with reason `unsubscribe` for that user's address and kind, never a bounce or a complaint.

The table must not keep email addresses in clear (CLAUDE.md, rule 8).

## Decision

- **Hashed addresses.** `email_hash` is HMAC-SHA256 of the trimmed, case-folded address under `CASERO_EMAIL_HASH_KEY`.
  - A plain SHA-256 would let anyone with a list of addresses test them against the table.
  - The key is permanent: only the hash is stored, so a new key would orphan every suppression. If it leaks, a migration re-keys from the addresses still known (users, waitlist) and records it in a new ADR. The other suppressions are lost, and their bounces show up again on the next send.
- **The `identity` module owns the list.** It is the lowest module, and every sender (complaints, verification, reminders) can read it through its own port. The worker's complaint job uses `SuppressionLookup` through the `SuppressedAddresses` port in `admin.application`.
- **Webhook at `POST /api/public/email-events`.** It runs in the `anonymous` context and reads the raw body, because SNS sends `text/plain`. It refuses a message when any of these fails:
  1. `TopicArn` equals `CASERO_SES_EVENTS_TOPIC_ARN`. This is checked first, so a foreign message never triggers a certificate download.
  2. `SignatureVersion` is `2` (SHA-256). The topic is configured that way, which avoids SHA-1.
  3. `SigningCertURL` is `https://sns.<region>.amazonaws.com/….pem`. The certificate is downloaded once and cached.
  4. The RSA signature over SNS's canonical string verifies.
- **Confirmation.** A `SubscriptionConfirmation` is confirmed with a GET to its `SubscribeURL`, and only if that URL is on an SNS host.
- **What suppresses.**
  - Only permanent bounces and complaints. A transient bounce says nothing about the address.
  - Repeats are idempotent through the table's `UNIQUE NULLS NOT DISTINCT (email_hash, email_kind)`.
- **When the check runs.** Before each send. A suppressed complaint copy is not sent: its job ends `failed` with code `suppressed`, and the inbox notice tells the owner to send it by hand.

## Consequences

- One more permanent secret in Bitwarden.
- A consumer who changes their email isn't suppressed under the new address, which is correct.
- The SNS signature and host rules are tested with a locally generated certificate and a mocked HTTP transport.
- Before launch, a real SES bounce is checked against the table (`docs/ops/email.md`).
