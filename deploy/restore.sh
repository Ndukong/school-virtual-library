#!/bin/sh
# School Virtual Library - restore (WP10).
#
# Restores the most recent nightly backup (or a specific one) into a
# FRESH database and media volume. This is a destructive drill: it drops and
# recreates the database inside the running stack. It must be EXECUTED once
# per term as a drill (documented in deploy/README.md).
#
# Usage:
#   deploy/restore.sh                       # restore BACKUP_DIR/latest
#   deploy/restore.sh /mnt/backup/svl/20260701-013000   # a specific backup
set -eu

STACK_DIR="$(CDPATH= cd "$(dirname "$0")" && pwd)"
COMPOSE="docker compose -f ${STACK_DIR}/docker-compose.prod.yml"
BACKUP_DIR="${BACKUP_DIR:-/mnt/backup/svl}"

if [ "$#" -ge 1 ]; then
  SOURCE="$1"
else
  SOURCE="${BACKUP_DIR}/latest"
fi

[ -f "${SOURCE}/db.dump.gz" ] || { echo "no db.dump.gz in ${SOURCE}" >&2; exit 1; }

set -a
# shellcheck source=/dev/null
. "${STACK_DIR}/.env.prod"
set +a

echo "WARNING: this drops the ${POSTGRES_DB} database and replaces media." >&2
echo "Restoring from ${SOURCE}" >&2

# 1. Drain the web container so it stops writing mid-restore.
${COMPOSE} stop web worker_documents worker_whatsapp

# 2. Drop + restore the database.
${COMPOSE} exec -T db psql -U "${POSTGRES_USER}" -d postgres \
  -c "DROP DATABASE IF EXISTS ${POSTGRES_DB};" \
  -c "CREATE DATABASE ${POSTGRES_DB} OWNER ${POSTGRES_USER};"
gunzip -c "${SOURCE}/db.dump.gz" | ${COMPOSE} exec -T db \
  pg_restore -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" --no-owner --no-privileges

# 3. Restore media into the volume.
if [ -f "${SOURCE}/media.tar.gz" ]; then
  docker run --rm \
    --volumes-from "$(${COMPOSE} ps -q web)" \
    -v "${SOURCE}:/backup:ro" \
    alpine:3.20 sh -c "rm -rf /srv/www/* && tar xzf /backup/media.tar.gz -C /srv"
fi

# 4. Bring the stack back up; a restore that boots into healthz=200 is a pass.
${COMPOSE} up -d
echo "restore finished; verify: curl -fsS https://\${DOMAIN}/healthz/"