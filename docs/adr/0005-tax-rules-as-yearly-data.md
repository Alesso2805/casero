# ADR-0005: Tax rules as yearly data and one declaration per renter document

- Status: Accepted
- Date: 2026-10-25
- Story: CS-01

## Context

Since 2026, a landlord pays a monthly Formulario 1683 per tenant document and collection month, on the rent actually collected. Rates, rounding, the cash threshold, the UIT and SUNAT's due-date schedule change by year and must be validated by an accountant. Wrong numbers hard-coded in the code would be a silent, recurring error.

## Decision

### Configuration as data

- `tax_rule_sets` has primary key `year`, with `rate_bp`, `deduction_bp`, `rounding`, `cash_threshold_cents`, `min_rent_bp`, `uit_cents` and `source_url`.
- `sunat_due_dates` has primary key `(year, period, ruc_group)`, where `year` is the year of the declared period.
- `holidays` lists national holidays, used for business days.
- The only source is `infra/seed/tax/{year}.yaml`, with an official source for every value.
  - 2026 is loaded by a data migration.
  - Later years are loaded by `make load-tax-config`, which runs as `casero_owner`, upserts, and is also run by the migrator at startup. It is idempotent, and it fails if a YAML lacks a `source_url`.
  - The admin panel only displays the data.
- No rate, date or SUNAT amount appears in domain code or in user-facing texts. Texts use variables such as `{umbral}` and `{multa_maxima}` (50 % of `uit_cents`).
- Tests use fixtures, not the seeds.

### Pure calculation

`tax.domain` exposes a pure function. Given the collected amount in cents and a rule set, it returns:

- `base_soles = round_half_up(collected_cents / 100)`
- `tribute_soles = round_half_up(base_soles × (10000 − deduction_bp) × rate_bp / 10^8)`

The arithmetic is integer only. The public calculator (CS-32) uses the same function. Reference case: 450.50 + 100.50 gives base 551 and tribute 28.

### Declarations, computed on read

- **Key:**
  - `(renter_doc_hmac, period)` (ADR-0007);
  - `(renter_id, period)` when the tenant has no document yet. Such a declaration is incomplete, and a SUNAT payment cannot be recorded until the document is filled in.
- **Amount:**
  - It sums the valid payments with `received_on` in the month, across all of the tenant's leases whose treatment is `standard` or `company_tenant`.
  - The part that the ledger allocation (ADR-0003) assigns to the opening balance of 2025 or earlier is excluded and shown apart for the accountant.
  - Credits never enter the base.
- **Rule set:** the one of the collection month's year.
- **Due date:** from `sunat_due_dates` by year, month and the account's RUC group.
  - Without a loaded schedule the card says "fecha por confirmar" and the worker alerts the owner.
  - Without a RUC, no due date is shown.
- **SUNAT payments:** recorded per declaration. Pending = tribute − valid SUNAT payments. The texts for changes after payment come from SPEC.md.
- **Plan gating:** declarations require `tax_module` and reminders require `tax_reminders`, both checked through `entitlements` (CS-07).

## Consequences

- A new year is a reviewed YAML change, not a code change.
- The yearly process (December) is part of operations. If the schedule is missing, the worker raises an alert.
- Primary key `year` cannot express a mid-year rule change. If the law changes within a year, the schema changes and a new ADR records it.
- A permanent document HMAC is required for grouping (ADR-0007).

## Enforcement

- Unit tests of the pure function with the validated cases.
- An architecture test forbidding numeric tax literals in `tax.domain`.
- Hypothesis properties in CS-21:
  - the tribute does not change when `created_at` is permuted among the movements of each day (ADR-0003 explains why);
  - a credit never changes the base of a month before its date.
- Cases validated by an accountant before the beta, including a credit registered after a payment that covered 2025 debt.
