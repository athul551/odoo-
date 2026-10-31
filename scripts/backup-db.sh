#!/usr/bin/env bash
# Dump the Brightloop database to backups/<db>-<timestamp>.sql.gz.
#
#   ./scripts/backup-db.sh
#   DB_NAME=brightloop_probe ./scripts/backup-db.sh
#
# Works with either `docker compose` (plugin) or `docker-compose` (standalone),
# so the dump comes from the same server the app talks to. The output is plain
# SQL, restorable with scripts/restore-db.sh.
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

SERVICE="${DB_SERVICE:-db}"
DB_NAME="${DB_NAME:-brightloop}"
DB_USER="${DB_USER:-brightloop}"
OUT_DIR="${BACKUP_DIR:-backups}"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$OUT_DIR/${DB_NAME}-${STAMP}.sql.gz"

mkdir -p "$OUT_DIR"

compose exec -T "$SERVICE" \
  pg_dump -U "$DB_USER" --no-owner --no-privileges "$DB_NAME" \
  | gzip > "$OUT"

echo "wrote $OUT ($(du -h "$OUT" | cut -f1))"
