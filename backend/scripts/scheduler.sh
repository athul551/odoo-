#!/usr/bin/env sh
# Brightloop nightly scheduler.
#
# Closes what the spec asks for but no code path triggered:
#   * "Some plans should close on their own when they end"  -> sweep_subscriptions
#   * "Nobody should be typing invoices by hand"            -> bill_day
#
# Run it once a day (cron, systemd timer, or a compose sidecar):
#   0 2 * * *  /srv/brightloop/backend/scripts/scheduler.sh >> /var/log/brightloop.log 2>&1
#
# Both commands exit non-zero when records failed, so a scheduler that alerts on
# non-zero exit will surface problems instead of silently dropping a customer.
set -eu

PYTHON="${BRIGHTLOOP_PYTHON:-python}"
HERE="$(cd "$(dirname "$0")" && pwd)"
MANAGE="${BRIGHTLOOP_MANAGE:-$HERE/../manage.py}"

echo "[$(date -Is)] billing day"
"$PYTHON" "$MANAGE" bill_day

echo "[$(date -Is)] sweep expired subscriptions"
"$PYTHON" "$MANAGE" sweep_subscriptions

echo "[$(date -Is)] done"
