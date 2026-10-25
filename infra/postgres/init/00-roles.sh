#!/usr/bin/env bash
set -euo pipefail

: "${CASERO_OWNER_PASSWORD:?}"
: "${CASERO_BACKUP_PASSWORD:?}"
: "${CASERO_APP_PASSWORD:?}"
: "${CASERO_WORKER_PASSWORD:?}"
: "${CASERO_ADMIN_PASSWORD:?}"

psql --set ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --set database="$POSTGRES_DB" \
  --set owner_password="$CASERO_OWNER_PASSWORD" \
  --set backup_password="$CASERO_BACKUP_PASSWORD" \
  --set app_password="$CASERO_APP_PASSWORD" \
  --set worker_password="$CASERO_WORKER_PASSWORD" \
  --set admin_password="$CASERO_ADMIN_PASSWORD" \
  --file /docker-entrypoint-initdb.d/sql/roles.sql
