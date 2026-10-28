#!/usr/bin/env bash
# Encrypted pg_dump every 6 hours to the backups bucket (CS-26, docs/ops/backups.md).
# casero_backup has BYPASSRLS, so the dump holds every account despite forced RLS.
set -euo pipefail

INTERVAL_SECONDS=21600
DISK_ALERT_PERCENT=80

ping() {
  if [[ -n "${1:-}" ]]; then
    curl --fail --silent --show-error --retry 3 --max-time 10 "$1" > /dev/null
  fi
}

back_up() {
  local stamp file
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  file="/tmp/casero-${stamp}.dump.age"
  # rate_limit_buckets only holds IP hashes meant to live 24 hours (ADR-0004).
  PGPASSWORD="$CASERO_BACKUP_PASSWORD" pg_dump \
    --host "${CASERO_BACKUP_DB_HOST:-postgres}" --username casero_backup --dbname casero \
    --format custom --exclude-table-data rate_limit_buckets \
    | age --recipient "$CASERO_BACKUP_AGE_RECIPIENT" > "$file"
  rclone copyto "$file" "${CASERO_BACKUP_TARGET}/casero-${stamp}.dump.age"
  rm -f "$file"
  echo "backup.uploaded casero-${stamp}.dump.age"
}

check_disk() {
  local used
  used="$(df --output=pcent /var/lib/postgresql/data | tail -1 | tr -dc '0-9')"
  # The monitor alerts when this heartbeat stops arriving.
  if (( used < DISK_ALERT_PERCENT )); then
    ping "${CASERO_DISK_HEARTBEAT_URL:-}"
  else
    echo "disk.above_threshold ${used}%"
  fi
}

: "${CASERO_BACKUP_PASSWORD:?missing}" "${CASERO_BACKUP_AGE_RECIPIENT:?missing}"
: "${CASERO_BACKUP_TARGET:?missing}"

if [[ "${1:-}" == "--once" ]]; then
  back_up
  exit 0
fi

while true; do
  # Bash ignores `set -e` inside a function called before `||`, so each backup runs as its
  # own process: any failed step fails the whole backup, and only a success pings.
  if "$0" --once; then
    ping "${CASERO_BACKUP_HEARTBEAT_URL:-}" || echo "backup.heartbeat_failed" >&2
  else
    echo "backup.failed" >&2
  fi
  check_disk || echo "disk.check_failed" >&2
  sleep "$INTERVAL_SECONDS"
done
