# ADR-0004: Cookie sessions and rate limits in PostgreSQL

- Status: Accepted
- Date: 2026-10-25
- Story: CS-01

## Context

Landlords use a PWA from their phones and the internal panel is used by one person. Sessions must be revocable, and login must resist brute force without letting anyone lock out someone else's account. The stack has no Redis and no second process to share state with.

## Decision

### Landlord sessions

- A random opaque token (32 bytes) goes in the cookie `__Host-casero_session`, with `HttpOnly`, `Secure`, `SameSite=Lax` and `Path=/`.
- The database stores only its SHA-256 in `sessions.token_hash`. No JWT.
- A new token is issued on every login. Sessions last 30 days, sliding. `last_seen_at` and `expires_at` are refreshed at most once per hour to limit writes.
- Logout revokes the session, and "close all sessions" revokes every session of the user. All expiry math uses `Clock.now()`.
- Passwords use Argon2id (argon2-cffi) and have at least 10 characters. CS-05 sets the parameters and measures them on the target server.

### CSRF

- Double-submit token: a cookie `__Host-casero_csrf` that JavaScript can read, echoed in an `X-CSRF-Token` header on every unsafe method.
- The login form also needs the token, so a pre-session token is issued before login. The `__Host-` prefix prevents cookie injection from subdomains.

### Staff sessions

- Cookie `__Host-casero_staff` with `SameSite=Strict`.
- Sessions live in `staff_sessions` and expire after 8 hours or after 30 minutes without use.
- Password plus mandatory TOTP (ADR-0008).

### Rate limits

- An `UNLOGGED` table, `rate_limit_buckets (key_hash, window_start, count)`, uses fixed windows incremented with an upsert. Losing its contents after a crash is acceptable.
- IP addresses are stored only as an HMAC with a salt that rotates.
- Per IP: blocking once a threshold is exceeded (HTTP 429).
- Per email: a progressive delay, never a lockout, so an attacker cannot block another person's account.
- The tenant portal and the public calculator are limited per link or per IP. Voucher uploads have their own quotas (3 pending per lease, 10 uploads per link per day).

### Local development

`__Host-` cookies need a secure context. They work on `http://localhost`. Testing from a phone on the local network uses Caddy's `tls internal`.

## Consequences

- No extra infrastructure. Sessions are revocable and visible in SQL.
- Each authenticated request may write to PostgreSQL for the sliding session and the rate limits. That is fine for a single process at Casero's scale.
- Rate-limit state disappears after a database crash, so limits briefly reset.

## Enforcement

CS-05 tests:

- session rotation on login;
- revocation and sliding expiry with a fake clock;
- CSRF on every unsafe method, including login;
- 429 per IP;
- delay per email without lockout.
