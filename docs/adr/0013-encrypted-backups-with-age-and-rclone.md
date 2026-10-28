# ADR-0013: Encrypted backups with age and rclone

- Status: Accepted
- Date: 2026-10-28
- Story: CS-26 (written after the critical review of Sprints 4–6)

## Context

SPEC asks for a `pg_dump` every 6 hours, encrypted and stored with a provider other than the server's, a monthly restore test that starts only from Bitwarden, and alerts when a backup does not arrive. Under forced RLS, a dump made by a normal role would hold no rows. A server compromise must not also expose the backups.

## Decision

- **Image and service:** a `backup` image built on `postgres:17` with `age`, `rclone` and `curl`. It runs `infra/backup/backup.sh` as the `backup` compose service, under the `backup` profile, so a deployment without backup accounts still starts.
- **Role:** the dump runs as `casero_backup`, the only role besides `casero_owner` with `BYPASSRLS`. It has `SELECT` on everything and no writes. `rate_limit_buckets` is left out, because it holds IP hashes meant to live 24 hours (ADR-0004).
- **Encryption:** the dump is piped into `age` with a **public** recipient. The private key never touches the server; it lives in Bitwarden. Someone who takes over the server can make new backups but cannot read the old ones.
- **Storage:** `rclone` copies each file to a Backblaze B2 bucket with object lock (30 days, compliance mode), using a key that can list and write but not delete (`docs/ops/storage-buckets.md`). Restores use a separate read key that lives only in Bitwarden.
- **Scheduling:** the loop lives in the container (every 6 hours), with no host cron. Each backup runs as its own process (`--once`), so any failed step fails the whole backup.
- **Monitoring:** Better Stack heartbeats. The backup heartbeat is pinged only after a confirmed upload. A disk heartbeat is pinged while the database volume is below 80 % full. A missing ping raises the alert.
- **Proof:** CI dumps as `casero_backup`, checks that the file holds no plaintext, restores it into an empty database and compares row counts table by table. It also checks that a failed backup neither uploads nor pings. The monthly manual restore follows `docs/ops/backups.md`.

## Consequences

- Up to 6 hours of records can be lost (SPEC). A restore takes the latest file, the private key from Bitwarden and a PostgreSQL 17 with the roles from `infra/postgres/init`.
- Losing the private key loses every backup. It is kept in Bitwarden, and the monthly test proves it still works.
- Purged accounts stay in the backups until object lock lets them expire after 30 days. The privacy policy says so.
