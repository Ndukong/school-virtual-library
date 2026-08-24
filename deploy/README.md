# WP10 production deployment

Target: one LAN box (Ubuntu Server) on the school wifi running the whole
stack under Docker Compose. TLS is terminated by Caddy next to the app; the
two queue workers are their own containers; PostgreSQL ships pgvector for the
planned vector search; nightlies back up to an external drive.

## Boot it

    cp deploy/.env.prod.example .env.prod
    # edit secrets: SECRET_KEY (random), POSTGRES_PASSWORD, DOMAIN, AI_*, WHATSAPP_*
    python -c "import secrets; print(secrets.token_urlsafe(50))"   # -> SECRET_KEY
    docker compose -f deploy/docker-compose.prod.yml up -d --build
    docker compose -f deploy/docker-compose.prod.yml exec web \
        python manage.py createsuperuser
    docker compose -f deploy/docker-compose.prod.yml exec web \
        python manage.py create_school_admin --school "School Name" --username admin1

Migrate once (new installs only; never on existing data):

    docker compose -f deploy/docker-compose.prod.yml exec web \
        python manage.py migrate

The container image already runs `collectstatic` on start; Whitenoise serves
`/static/` directly from `STATIC_ROOT` inside the image. `/media/` (uploaded
documents) is the shared `media` volume - the library app never serves it
publicly, only through the controlled views.

## Operations

- Health: `curl -fsS https://$DOMAIN/healthz/` (returns 200 with
  `application/json`; the Caddy stack healthchecks the web container against
  it, and the boot guard refuses DEBUG=False with the dev SECRET_KEY).
- Workers: `docker compose logs -f worker_documents worker_whatsapp`.
- Search on pgvector: `SEARCH_PGVECTOR_DIM=768` is wired; after switching to
  PostgreSQL, backfill vectors with
  `docker compose … exec web python manage.py backfill_pg_vectors`.

## Backups and the restore drill (MUST be executed, once per term)

Both scripts need the stack's `.env.prod`, `pg_dump`/`pg_restore` availability
(they shell into the `db` container so nothing extra is required the host),
and `BACKUP_DIR` mounted to the external drive.

    BACKUP_DIR=/mnt/backup/svl deploy/backup.sh          # nightly (systemd timer)
    deploy/restore.sh                                     # drills BACKUP_DIR/latest

The restore drill destroys and recreates the database from the last backup
and repopulates media. Success criterion for the drill: the stack boots, the
web container is healthy, and `/healthz/` returns 200 with entries visible in
the admin. Timezone for the nightly schedule is Africa/Douala.

## CI

`.github/workflows/ci.yml` runs the full gate (ruff, check, makemigrations
--check, full suite under `settings_test`, `check --deploy` with production
env, pip-audit, and a locale-freshness check) on every push/PR, on Ubuntu
(py3.12) and Windows (py3.10, the local dev target).