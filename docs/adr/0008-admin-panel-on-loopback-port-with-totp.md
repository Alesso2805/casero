# ADR-0008: Internal admin panel in the same process, on a loopback-only port reached through SSH, with TOTP

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

A separate admin service would mean another deployment to maintain, and a private network service (a VPN or mesh) would add cost or another dependency. The panel must never reach tenants, leases, payments or files, and it should not be reachable from the internet at all.

## Decision

### Process and database

- The panel runs in the same Python process as the API. When `ADMIN_ENABLED=true`, the process starts a second Uvicorn server in the same event loop. It serves only `/api/admin/*` and the built `/admin` bundle.
- The public app does not mount those routes at all.
- The admin app uses its own SQLAlchemy pool as `casero_admin`:
  - without `BYPASSRLS`;
  - with policies only on `accounts`, `subscriptions` and `subscription_payments`;
  - with the column grants of SPEC.md, including `UPDATE(founder)` on `subscriptions`;
  - with read-only access to the tax configuration (ADR-0002, ADR-0005).

### Network

- The admin listener is published only on the server's `127.0.0.1` (for example `127.0.0.1:8081:8081` in Docker Compose). Nothing on a public interface listens for it.
- The owner opens it through an SSH tunnel: `ssh -L 8081:127.0.0.1:8081 <server>`, then `http://localhost:8081/admin` in the browser.
- SSH accepts only keys and no root login. The owner's SSH key lives in Bitwarden.
- On the public domain, Caddy answers 404 for `/admin` and `/api/admin/*`. That is a second barrier on top of the public app not having those routes.
- Caddy is not in front of the admin listener, so the admin app sets its own security headers (CSP, `frame-ancestors 'none'`, `Referrer-Policy: no-referrer`) and its own request size limit.

### Authentication

- Staff users are created only with `make create-staff`, which runs as `casero_owner`, never over HTTP.
- Login requires an Argon2id password plus a TOTP code (pyotp, RFC 6238, 30-second steps, one step of tolerance).
- Recovery codes are stored hashed and each one is removed from the array when used.
- The session cookie is `__Host-casero_staff` with `SameSite=Strict`. Browsers treat `http://localhost` as a secure context, so the `Secure` cookie works through the tunnel in Chromium and Firefox. The cookie is bound to `localhost`, a different host from the public app.
- Sessions live in `staff_sessions` and expire after 8 hours or after 30 minutes idle. CSRF works as in ADR-0004.

### Audit

- Every panel action and every staff `make` command writes `staff_audit_log`.
- Before any staff user exists, the commands write `staff_user_id` as null and `actor = 'cli'`.

### Commands

`make invite`, `make grant-founder` and `make complaint-respond` run as `casero_admin`. `make create-staff` and `make load-tax-config` run as `casero_owner`.

## Consequences

- No extra service and no extra cost. The panel is unreachable from the internet.
- Three independent barriers protect it: SSH access to the server, TOTP, and database policies.
- A bug in an admin route still runs inside the API process, but its role cannot see landlord data beyond accounts and subscriptions.
- The owner needs SSH access from their device. If the device is lost, the key is restored from Bitwarden and the TOTP recovery codes still work.
- Headers and limits that Caddy provides for the public site must be set in the admin app itself.

## Enforcement

- A test that the public app does not mount `/api/admin/*`.
- A test that the admin server is not started when `ADMIN_ENABLED` is false.
- A check of the Compose file that the admin port is published only on `127.0.0.1`.
- A test that Caddy answers 404 for `/admin` and `/api/admin/*` on the public site.
- Tests for the admin security headers.
- TOTP, recovery-code and session-expiry tests with a fake clock.
- A test that `casero_admin` sees no rows of an account table without its policy, even after a temporary grant in the test.
