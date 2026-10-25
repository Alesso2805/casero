# ADR-0008: Internal admin panel in the same process, reachable only through Tailscale, with TOTP

- Status: Accepted
- Date: 2026-10-25
- Story: CS-01

## Context

The owner needs to:

- look up accounts;
- record Yape payments and extend subscriptions;
- grant founder status;
- answer complaints within the legal deadline;
- check the SUNAT schedule and failed jobs.

A separate admin service would mean another deployment to maintain. The panel must never reach tenants, leases, payments or files.

## Decision

### Process and database

- The panel runs in the same FastAPI process. `/api/admin/*` is mounted only when `ADMIN_ENABLED=true`.
- It uses its own SQLAlchemy pool as `casero_admin`:
  - without `BYPASSRLS`;
  - with policies only on `accounts`, `subscriptions` and `subscription_payments`;
  - with the column grants of SPEC.md, including `UPDATE(founder)` on `subscriptions`;
  - with read-only access to the tax configuration (ADR-0002, ADR-0005).

### Network

- Caddy serves `/admin` and `/api/admin/*` only to addresses in the Tailscale range `100.64.0.0/10`. On the public hostname those paths return 404.
- The owner reaches the panel through the server's Tailscale (MagicDNS) hostname, with the certificate Caddy obtains from the local `tailscaled`.
- The staff cookie is therefore bound to a different origin from the public app.

### Authentication

- Staff users are created only with `make create-staff`, which runs as `casero_owner`, never over HTTP.
- Login requires an Argon2id password plus a TOTP code (pyotp, RFC 6238, 30-second steps, one step of tolerance).
- Recovery codes are stored hashed and each one is removed from the array when used.
- The session cookie is `__Host-casero_staff` with `SameSite=Strict`. Sessions live in `staff_sessions` and expire after 8 hours or after 30 minutes idle. CSRF works as in ADR-0004.

### Audit

- Every panel action and every staff `make` command writes `staff_audit_log`.
- Before any staff user exists, the commands write `staff_user_id` as null and `actor = 'cli'`.

### Commands

`make invite`, `make grant-founder` and `make complaint-respond` run as `casero_admin`. `make create-staff` and `make load-tax-config` run as `casero_owner`.

## Consequences

- No extra service to deploy. Three independent barriers protect the panel: network restriction, TOTP and database policies.
- A bug in an admin route runs inside the public API process, but its role cannot see landlord data beyond accounts and subscriptions.
- Access depends on Tailscale. If the owner's device is lost, recovery codes and `make` commands over SSH remain available.
- **Open point, pending decision.** Tailscale's free Personal plan is for non-commercial use. Using it for a business needs a paid plan, or an equivalent private network (for example plain WireGuard) with the same address-range rule in Caddy. To be decided before CS-24.

## Enforcement

- A test that `/api/admin/*` is not mounted when `ADMIN_ENABLED` is false.
- A header and allowlist test in the Caddy configuration.
- TOTP, recovery-code and session-expiry tests with a fake clock.
- A test that `casero_admin` sees no rows of an account table without its policy, even after a temporary grant in the test.
