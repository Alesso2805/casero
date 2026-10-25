# ADR-0003: Append-only ledger and state derived on read

- Status: Accepted
- Date: 2026-10-25
- Story: CS-01

## Context

Balances, charge statuses and tax declarations must be correct for any sequence of entries, corrections and voids. Clients on weak mobile connections retry requests, and the history must be auditable.

## Decision

### Append-only tables

`charges`, `charge_voids`, `payments`, `payment_voids`, `deposits`, `deposit_voids`, `deposit_movements`, `deposit_movement_voids`, `lease_rent_changes`, `tax_payments`, `tax_payment_voids`, `legal_acceptances`, `legal_withdrawals`, `reminder_logs`, `audit_log` and `staff_audit_log` are never updated or deleted.

- No application role has UPDATE or DELETE on them. The only exception is `purge_account()` (ADR-0007).
- A correction is a new row that references the original:
  - a void keyed by the voided record;
  - a `rent_correction` with `corrects_charge_id`;
  - a later `lease_rent_changes` row for the same period.
- Concurrency checks lock the lease row (`SELECT ... FROM leases ... FOR UPDATE`) or the account row, never a ledger row.

### Money

- Amounts are integer cents of soles: `bigint` in PostgreSQL, `int` in Python and an integer `number` in TypeScript.
- No `float` anywhere in money paths. Rounding to whole soles is integer arithmetic.

### Identifiers and idempotency

- All primary keys are uuid v7.
- The client generates the id for what the landlord creates: payments, manual charges (adjustment, rent correction, opening balance), deposits, deposit refunds, rent changes and SUNAT payments.
- Everything else gets a server-generated id: `audit_log`, `legal_acceptances`, `legal_withdrawals`, `reminder_logs`, `staff_audit_log` and the worker's `rent` charges.
- Creating a client-identified record runs `INSERT ... ON CONFLICT (id) DO NOTHING RETURNING ...`. If nothing is returned, the application reads the id under RLS:

  | Result of the read | Response |
  | --- | --- |
  | Found, same content | 200 with the existing record |
  | Found, different content | 409 without detail |
  | Not found (the id belongs to another account) | 409 without detail |

- Void tables have no `id`. Their primary key is the voided record's key, with a composite foreign key `(account_id, x_id)`. Voiding is idempotent through that key: repeating it returns 200 and the existing void.
- `UNIQUE (account_id, id)` exists on every account table that has an `id`.
- `created_at` is set by the application from `Clock.now()`. Ledger tables have no `DEFAULT now()`.

### Derived state

Nothing below is stored. Each is computed on read from the valid rows, which are rows without a void:

- the balance;
- the allocation of payments and credits to charges;
- charge statuses;
- deposit availability;
- subscription status;
- tax declarations.

The balance of a lease is Σ valid charges (adjustments are signed) − Σ valid payments.

### Allocation

- **Receiving charges:** valid charges with a positive amount, ordered as follows:
  1. the opening balance for 2025 or earlier;
  2. the opening balance for 2026;
  3. then by `due_date`, `created_at` and `id`.
- **Movements:** valid payments and credits (negative adjustments) together, ordered by effective date.
  - A payment's effective date is `received_on`.
  - A credit's effective date is the Lima date of its `created_at`.
  - On the same date, all payments come first and all credits after. Within each group the order is `(created_at, id)`.
- **Waterfall:** each movement fills what earlier movements left unpaid, in charge order. A movement therefore affects only the allocation of later movements. Any surplus stays as credit and covers the following charges.

The allocation function lives in `ledger.domain`. `tax` uses it through `ledger.application`, so balances and tax always use the same allocation.

### Why the tax does not depend on insertion order

Insertion order appears only in `created_at`, and `created_at` only breaks ties between movements of the same group on the same date. Those ties cannot change balances or the tax:

- **Blocks depend only on their total.** The waterfall fills charges in a fixed order. When a block of consecutive movements is applied, what each charge receives, and the surplus, depend only on the block's total, not on the order inside it.
- **Payments of one date.** They form one block, because the credits of that date come after them. How much of the block covers the opening balance of 2025 or earlier (excluded from the base) depends only on the block's total. All those payments belong to the same lease and the same month, so the base of that month is the same in any order.
- **Credits of one date.** They form the next block. Credits never enter the base, and what they leave unpaid depends only on their total, so later movements see the same state.
- **Movements on different dates.** They are ordered by date, which does not depend on insertion.

Only the mapping of individual movements to individual charges inside a block can change with insertion order, and neither balances nor the tax depend on it.

## Consequences

- Voiding never leaves inconsistent data, and every change is visible in the history.
- Reads do more work than with stored balances. With at most 10 leases per account, this is negligible. A cache would need a new ADR.
- Retried requests never duplicate records, and conflicting retries are visible as 409.
- A credit registered on the same day as a payment never takes the 2025 opening balance away from that payment, because payments of a date are applied before its credits.

## Enforcement

- Catalog test for grants and defaults (CS-03).
- Hypothesis properties in CS-12 and CS-31: for any sequence of charges, corrections, credits, payments and voids:
  - the balance formula holds;
  - each charge's balance and each declaration's tax do not change when `created_at` is permuted among the movements of each day;
  - a movement never changes the allocation of earlier movements.
- Resubmission tests for every client-identified POST, including the 409 cases.
