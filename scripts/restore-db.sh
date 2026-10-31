#!/usr/bin/env bash
# Restore a dump produced by scripts/backup-db.sh.
#
#   ./scripts/restore-db.sh backups/brightloop-20261031-151500.sql.gz
#
# The dump is plain SQL without --clean, so restore into an empty database. To
# replace an existing one, drop and recreate it first:
#
#   docker-compose exec -T db psql -U brightloop -d postgres \
#     -c 'DROP DATABASE brightloop;' -c 'CREATE DATABASE brightloop OWNER brightloop;'
#   ./scripts/restore-db.sh backups/<file>.sql.gz
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

compose() {
  if docker compose version >/dev/null 2>&1; then
    docker compose "$@"
  else
    docker-compose "$@"
  fi
}

FILE="${1:?usage: $0 <backup.sql.gz>}"
SERVICE="${DB_SERVICE:-db}"
DB_NAME="${DB_NAME:-brightloop}"
DB_USER="${DB_USER:-brightloop}"

[ -f "$FILE" ] || { echo "no such backup: $FILE" >&2; exit 1; }

gunzip -c "$FILE" \
  | compose exec -T "$SERVICE" psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1

echo "restored $FILE into $DB_NAME"
