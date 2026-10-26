# ADR-0002: Database access contexts, roles and row-level security

- Status: Accepted
- Date: 2026-10-25
- Story: CS-01

## Context

Every landlord's tenants, payments and tax data live in one PostgreSQL database. Isolation between accounts, and between tenants of the same landlord in the tenant portal, must hold even when application code forgets a filter. The API, the worker and the internal panel each need different reach.

## Decision

### Roles

The exhaustive grant list lives in the roles table of SPEC.md. In summary:

| Role | Used by | Notes |
| --- | --- | --- |
| `casero_owner` | Migrations, `make create-staff`, `make load-tax-config` | Owns every object and every `SECURITY DEFINER` function. Has `BYPASSRLS` because `FORCE` would otherwise subject the owner to the policies |
| `casero_backup` | `pg_dump` | `LOGIN`, `BYPASSRLS`, read-only |
| `casero_app` | API: `anonymous`, `account` and `tenant` contexts | No `BYPASSRLS`; no UPDATE or DELETE on ledger tables |
| `casero_worker` | Worker: `system` context | No `BYPASSRLS`; same account-table grants as `casero_app`, plus the system tables |
| `casero_admin` | Internal panel and staff `make` commands | No `BYPASSRLS`; column grants plus its own policies (below) |

No role used by the API, the worker or the panel owns tables or has `BYPASSRLS`.

### Row-level security

- Every table in `public`, except the closed list of SPEC.md, has `ENABLE` and `FORCE ROW LEVEL SECURITY`.
- The account policy, for both `USING` and `WITH CHECK`, is `account_id = NULLIF(current_setting('app.account_id', true), '')::uuid`; on `accounts` it compares `id`. A missing or empty setting yields `NULL`, so no row matches.
- Tenant scope, as `AS RESTRICTIVE` policies:
  - The condition is `current_setting('app.context', true) IS DISTINCT FROM 'tenant' OR lease_id = NULLIF(current_setting('app.lease_id', true), '')::uuid`. `leases` compares `id`.
  - Tables without `lease_id` use `EXISTS` on their parent: voids, deposit movements and files. `renters`, `units` and `properties` use `EXISTS` on the lease.
  - `accounts` and `subscriptions` stay visible while `app.lease_id` is set, because the portal needs the landlord's name and the plan features. The `/api/tenant/*` endpoints still read only `display_name` and the plan features, through an explicit DTO. Every other account table is invisible in the tenant context.
  - When `app.context = 'tenant'` and `app.lease_id` is missing, the comparison is `NULL` and nothing is visible: the context fails closed.
- `casero_admin` policies: `TO casero_admin` policies exist only on `accounts`, `subscriptions` and `subscription_payments`, for the commands its grants allow. On every other account table it sees no rows even if a grant is added by mistake.

### Contexts

- **`anonymous`** (`/api/public/*`): `app.account_id` is not set. It touches only tables without RLS and reads the plan and tax configuration. It has two exceptions:
  - Registration: the application generates the account id, runs `set_config('app.account_id', id, true)` and inserts the account, member, legal acceptances and subscription in one transaction.
  - Cancelling an account deletion from the email link: `app_cancel_deletion(p_token_hash, p_now)`.
- **`account`** (`/api/app/*`): the `current_account` dependency resolves the session to its account through `account_members` and runs `set_config('app.account_id', :id, true)` with a bound parameter inside the request transaction.
- **`tenant`** (`/api/tenant/*`):
  - `app_resolve_tenant_token(p_hash, p_today)` returns the account and lease when the link is not revoked, its lease is active or ended less than 90 days before `p_today`, and the account has not asked to be deleted.
  - A single statement then sets `app.account_id`, `app.context = 'tenant'` and `app.lease_id`, all transaction-local.
- **`system`** (worker as `casero_worker`): `app_list_account_ids(p_purpose, p_today)`, with `p_purpose` ∈ `jobs`, `purge`, lists the accounts. Each account is then processed in its own transaction with `app.account_id` set. `job_runs` and `pending_object_deletions` have no RLS.
- **`admin`** (`/api/admin/*`): a separate loopback-only listener and a separate pool as `casero_admin`, both created only when `ADMIN_ENABLED=true` (ADR-0008).

Settings are always set with `set_config(name, :value, true)` and bound parameters, never with interpolated `SET` statements.

### `SECURITY DEFINER` functions

| Function | Executable by | Purpose |
| --- | --- | --- |
| `app_resolve_tenant_token(p_hash, p_today)` | `casero_app` | Resolve a tenant link to its account and lease |
| `app_cancel_deletion(p_token_hash, p_now)` | `casero_app` | Validate the single-use token, clear the deletion schedule, clear and return `deletion_contact_enc`. The application decrypts it and restores the user's email in the same transaction |
| `app_list_account_ids(p_purpose, p_today)` | `casero_worker` | List accounts for scheduled jobs or for purge |
| `purge_account(p_account_id, p_today, p_email)` | `casero_worker` | Delete an account whose scheduled deletion has passed (ADR-0007). `p_email` is used only to delete that email's invites and is never logged |

All four are owned by `casero_owner`, set a fixed `search_path`, validate their arguments, receive dates as parameters instead of calling `CURRENT_DATE` or `now()`, and have `EXECUTE` revoked from `PUBLIC`.

## Consequences

- Isolation does not depend on application code remembering a filter.
- The tenant portal has a second, independent barrier against showing one tenant another tenant's data.
- Every new table needs its policies. The catalog test catches a missing one.
- The `EXISTS` policies cost a little on each read. This is irrelevant at Casero's scale.
- Writing voucher files in the tenant context needs care in CS-19. A file row is inserted before the voucher that references it, and deduplication by hash must not see files of other leases. CS-19 designs that path within these policies.
- The four functions are the privileged surface. They stay minimal and each has its own tests.

## Enforcement (CS-03, then every story)

- Catalog test:
  - forced RLS on every table outside the closed list;
  - grants exactly as in the roles table;
  - function `EXECUTE` grants;
  - no `DEFAULT now()` on ledger tables.
- Tests that set `app.context = 'tenant'` without `app.lease_id` and see no rows.
- Tests that `casero_app` gets "permission denied" on `app_list_account_ids` and `purge_account`.
- Tests that the functions work with `app.account_id` empty.
- Two-account tests on every endpoint (CS-07 onwards).
- A test that no `/api/tenant/*` response contains the landlord's RUC or email (CS-18).
