#!/bin/sh
# School Virtual Library - nightly backup (WP10).
#
# Backs up the PostgreSQL database and the uploaded-files media volume to an
# external drive mounted at BACKUP_DIR. Intended to run from a systemd timer
# on the LAN box:
#
#     [Unit] Description=svl nightly backup
#     [Timer] OnCalendar=*-*-* 01:30 Africa/Douala; Persistent=true
#     [Service] Type=oneshot; ExecStart=/opt/svl/deploy/backup.sh
#
# Requires: docker compose v2 and pg_dump (or a db container with pg_dump).
set -eu

STACK_DIR="$(CDPATH= cd "$(dirname "$0")" && pwd)"
COMPOSE="docker compose -f ${STACK_DIR}/docker-compose.prod.yml"
BACKUP_DIR="${BACKUP_DIR:-/mnt/backup/svl}"
STAMP="$(date +%Y%m%d-%H%M%S)"
TARGET_DIR="${BACKUP_DIR}/${STAMP}"

mkdir -p "${TARGET_DIR}" "${BACKUP_DIR}/latest"

# 1. SQL dump (custom format; restorable with pg_restore).
#    Requires the POSTGRES_* variables from the stack's .env.prod.
set -a
# shellcheck source=/dev/null
. "${STACK_DIR}/.env.prod"
set +a
${COMPOSE} exec -T db pg_dump -U "${POSTGRES_USER}" -Fc "${POSTGRES_DB}" \
  | gzip -9 > "${TARGET_DIR}/db.dump.gz"

# 2. Media (uploaded documents) as a tar stream from the volume.
docker run --rm \
  --volumes-from "$(docker compose -f "${STACK_DIR}/docker-compose.prod.yml" ps -q web)" \
  -v "${TARGET_DIR}:/backup:ro" \
  alpine:3.20 tar czf /backup/media.tar.gz -C /srv www

# 3. Keep a stable 'latest' pointer for a quick restore drill.
rm -f "${BACKUP_DIR}/latest/db.dump.gz" "${BACKUP_DIR}/latest/media.tar.gz"
cp "${TARGET_DIR}/db.dump.gz" "${BACKUP_DIR}/latest/db.dump.gz"
cp "${TARGET_DIR}/media.tar.gz" "${BACKUP_DIR}/latest/media.tar.gz"

echo "backup complete -> ${TARGET_DIR}"