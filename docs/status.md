# Project status

**Source of truth for phase state.** README.md is a description of the
project; this file is what is actually true right now.

| | |
|---|---|
| Last verified | 2026-08-23 |
| Phases complete | 0-10 |
| Current phase | 11 - PWA (in progress) |
| Gate status | red - see open defects |
| Test count | 100+ (verify with the suite, do not trust this number) |

## Open defects (fix before new features)

1. ~~`library/views.py` - `Resource.chapters.none()` should be
   `resource.chapters.none()`. Non-book resource detail pages crash.~~
   **CLOSED in WP1** (test covers every resource type).
2. ~~`requirements.txt` is missing psycopg; the PostgreSQL path cannot boot.~~
   **CLOSED in WP1** (pinned deps + dj-database-url; PG URL boots — settings
   module proof).
3. `search/services.py` - keyword ranking slices an id-ordered queryset,
   silently dropping matches in later resources. (WP5)
4. `search/services.py` - every embedding is loaded into memory per query.
   (WP5)
5. `whatsapp/views.py` - retrieval and LLM work runs inside the webhook,
   and exception text is sent to users. (WP6)
6. ~~No LOGGING config, no health endpoint, no CI.~~ **Partly closed in WP1**:
   LOGGING (console + rotating file) and `/healthz/` done; CI is WP10.
7. ~~Rate limiting counts rows without a lock; concurrent requests slip past.~~
   **CLOSED in WP2**: atomic cache counter (per-minute bucket, TTL) with the
   DB count as a fallback; the blanket superuser exemption is gone
   (explicit flag, default off).
8. ~~Silent truncation of user input.~~ **CLOSED in WP1**: questions over
   5000 chars are rejected with a user-facing message, never truncated.

## Work Package 3 - file serving and abuse control (2026-08-23, branch
wp/3-file-serving)

- Hardened file views: nosniff, same-origin CORP, `private, no-store`, and a
  sandboxing CSP on inline reads; HTTP Range (206/416), ETag/Last-Modified
  with If-None-Match/If-Modified-Since (304) so multi-MB PDFs are not
  re-fetched on seek; X-Accel-Redirect mode (LIBRARY_XACCEL_ENABLED) so the
  app server stops streaming file bytes behind a reverse proxy.
- Download abuse control: per-minute burst + per-local-day cap enforced off
  ResourceAccessEvent (429), superusers exempt; reports page shows today's
  per-user downloads and flags users over the cap.
- Watermarking: LICENSED/OWNED inline reads render a sandboxed-iframe page
  with a name+timestamp footer (streamed via /library/<id>/stream/); other
  material reads inline unchanged.
- Login lockout: exponential backoff keyed on username+IP (LoginFailure
  audit rows + LoginLock), users inside a lock window never reach the auth
  backend; admin unlock action; success clears the key.
- Admin password reset for students: temporary password (validator-safe),
  printable one-time slip (session-held, cleared after render), forced change
  on first login (LoginView redirect + MustChangePasswordMiddleware blocking
  all other pages), PasswordReset audit row (who reset whom, completed_at).
- LoginView.form_valid fixed to authenticate before the forced-change
  redirect (previously left the user logged out).

Gate: ruff 90 (86 baseline + 4 pre-existing RUF012; WP3 files zero); check
clean; check --deploy exit 0; 345 tests OK (3 skipped); pip-audit clean.

## Work Package 4 - OCR (2026-08-23, branch wp/4-ocr)

- `documents/ocr.py`: OCR runs between EXTRACT and CHUNK for blank pages.
  Real engine = ocrmypdf (needs Tesseract + Ghostscript on PATH, languages
  eng,fra via DOCUMENTS_OCR_LANGUAGES); deterministic fake engine behind
  DOCUMENTS_OCR_FAKE_ENGINE for tests.
- Per-page progress ProcessingLog INFO, resumability (needs_ocr && ocr_at
  null), per-resource timeout + page cap (DOCUMENTS_OCR_TIMEOUT_SECONDS /
  DOCUMENTS_OCR_MAX_PAGES). Low-confidence (<0.4) pages log WARNING and set
  Resource.needs_teacher_review along with any still-needs_ocr pages. Text is
  never fabricated: unreadable-after-OCR pages stay flagged.
- Behavior change (WP4 spec): a fully-scanned set no longer fails the
  resource - it is flagged for OCR/review and can still reach READY (CHUNK
  tolerates zero chunks, EMBED tolerates an empty set). Corruption still
  fails cleanly before OCR.
- DEPLOYMENT CAVEAT: this machine has no Tesseract binary, so the live OCR
  path is unverified here; the whole pipeline is exercised through the fake
  engine. To enable real OCR on the school box install tesseract + ghostscript
  and confirm `tesseract --version`, then uploads auto-OCR blank pages
  (eng/fra).

Gate: ruff 90 (WP4 files zero new); check clean; 352 tests OK (3 skipped);
check --deploy exit 0; pip-audit clean.

## Work Package 5 - search performance and cost (2026-08-23, branch wp/5-search)

- Keyword recall: the arbitrary id-ordered [:500] slice is gone; keyword
  ranking considers every permission-filtered match (regression test with
  520 filler chunks + a late match).
- pgvector path behind one interface (search/backends): ORDER BY embedding
  <-> distance over the permission-filtered id set on PostgreSQL, HNSW
  index; conditional migration (no-op outside PG) + `backfill_pg_vectors`
  command copies JSON ChunkEmbedding vectors into the vector column. SQLite
  keeps the Python-cosine fallback only.
- Local embeddings: fastembed (multilingual-e5-small) provider registered as
  'local', recommended for a school box with no cloud spend; remote providers
  stay selectable. No API key required.
- Caches: per-model query-embedding cache; RAG answers cached per (school,
  scope, prompt version, chat model, normalized question, school resource
  version) with RAG_USE_CACHE/RAG_CACHE_TTL; any resource change invalidates.
  Cache hits still audit to AIInteraction (used_provider=False).
- Budgets/quota: per-school daily/monthly request+token budgets counted on
  AIRequestLog (local-time windows; BudgetExceeded is RateLimited so views/
  WhatsApp render friendly messages), SCHOOL_STORAGE_QUOTA_MB at upload, and
  DOCUMENTS_MAX_CHUNKS cap with WARNING.
- `manage.py benchmark_search` reports p50/p95 for keyword/semantic/hybrid on
  a seeded corpus.

Gate: ruff 92 (86 baseline + pre-existing RUF012/F811/B905; every WP5 file is
zero); check clean; 367 tests OK (3 skipped); check --deploy exit 0;
pip-audit clean.

DEPLOYMENT NOTE (live OCR): tesseract/ghostscript not on this box; WP4 live
OCR path remains verified via the fake engine until binaries are installed.

## Work Package 6 - WhatsApp reliability (2026-08-23, branch wp/6-whatsapp)

- Webhook is now sub-second: it verifies, persists each inbound as a
  WhatsAppTask (dedup by message_id on WhatsAppMessage), and returns 200.
- All handling (linking, routing, replies, throttling) happens in the
  database-backed queue drained by `python manage.py process_whatsapp`
  (atomic claim + attempt bump; FAILED after max attempts).
- Never sends exception text: on any handler failure the worker logs the full
  traceback under the task correlation id (public_id) and the user receives
  GENERIC_APOLOGY only.
- Outbound reliability: send_message retries the provider twice internally
  (tested via urlopen flap), obeys the Meta 24h reply window
  (WHATSAPP_MESSAGE_WINDOW_HOURS, only replies to recent inbound), and a
  per-phone daily outbound cap (WHATSAPP_DAILY_MESSAGE_CAP).
- Admin kill switch: WhatsAppKillSwitch singleton + `whatsapp_switch on|off|
  status` command; when disabled the webhook drops payloads (still 200) and
  the worker no-ops.

Gate: ruff 94 (pre-existing only; WP6 files zero); check clean; 374 tests OK
(3 skipped); check --deploy exit 0; pip-audit clean.

## Work Package 7 - Bilingual en/fr (2026-08-24, branch wp/7-i18n)

- Infrastructure: LANGUAGES + LOCALE_PATHS + LocaleMiddleware; a per-user
  User.language field (additive migrations accounts.0004, question_bank.0002);
  UserLanguageMiddleware overrides the request language from the signed-in
  account (falls back to the django_language cookie, Django 5.2 style); a
  /language/ switcher persists the choice to the account and writes the
  language cookie, safe same-origin next validation (anonymous visitors can
  switch so the login screen is bilingual too).
- AI language-awareness: the RAG and study system prompts are extended per
  call with a language instruction (rag-v2 / study-v2); the "no material"
  refusal and the transient-outage message are localized; the answer cache
  key now includes the user language so a cached English answer never leaks
  to a francophone student. Quoted source passages stay verbatim.
- Content tagging: Resource.language free text is normalized to en/fr on
  upload (form select + synonym mapping for legacy rows); Question.language
  added; library list, search and practice can all filter by language
  (permission filtering still happens before every retrieval).
- Catalog: French final catalog locale/fr/LC_MESSAGES/django.po (hand
  maintained; the Windows dev image has no GNU gettext), compiled to
  django.mo via tools/compile_messages.py (Babel, dev-only dependency).
  Core user flows are translated (base/nav, login, dashboards, profile,
  library list/detail/upload, search, AI ask/answer, practice home/attempt/
  progress). Deep teacher/admin pages (exam builder, reports, question list,
  admin area) remain English for a later pass.
- Tests: +20 (switcher persistence + cookie, French UI on /profile/, French
  login for anonymous switchers, French system-prompt instruction via a
  recording provider, French + English refusals offline, rag-v2 prompt
  version, resource language list/upload normalization, search language
  scope, question language practice filter, practice language selector).

Gate: ruff 97 (no new findings from WP7 files); check clean; 394 tests OK
(3 skipped); check --deploy exit 0; pip-audit clean; migrations reversible
and generated from scratch, makemigrations --check clean.

## Work Package 8 - Offline-first PWA (2026-08-24, branch wp/8-offline)

- Privacy fix: the worker no longer auto-caches authenticated pages. It now
  precaches ONLY the static shell (/offline/, site.css, manifest) and serves
  everything else NETWORK FIRST, falling back to caches the USER explicitly
  built from the page (svl-files-v1 / svl-attempts-v1). Logging out lands on
  /login/ where offline-clear.js erases both device caches (shared labs).
- Opt-in offline reading: the resource page shows an "Offline reading" panel
  (data cost shown before saving, translated). Saving caches the read page
  plus its PDF stream; offline navigation re-opens the exact document from
  cache (watermark reader intact), never stale cache for other content.
- Offline practice: the attempt page ships a "Take this quiz offline" button
  (caches the quiz) and an offline fallback: submissions made while offline
  are queued in localStorage and replayed in order on `online`/next visit
  against the SAME submit endpoint, so server-side ownership/validity still
  apply. Session-expiry is detected (redirect to login keeps the queue).
- CSS: .btn-row now wraps (horizontal overflow at 360px fixed). Reader and
  practice i18n strings added to the French catalog.
- Tests: +16 unit tests (worker never opens non-shell caches; precache gated
  to the shell; offline bundles shipped; manifest lang follows active
  language; bilingual offline shell; cache-clear on login; resource detail
  panel present/absent by file & 404 cross-school; attempt form offline
  markers + submit-URL parity).
- Browser proof (Playwright, 360px): logged in as a seeded student, saved a
  PDF for offline, confirmed both URLs in svl-files-v1, then went offline and
  reopened the reader - the watermark page and the embedded PDF served from
  cache (no /offline/ shell); uncached navigation fell back to the shell.

Gate: ruff 97 (no new from WP8 files); check clean; 404 tests OK (3 skipped);
check --deploy exit 0; pip-audit clean.

## Work Package 9 - Safeguarding, privacy, governance (2026-08-24,
branch wp/9-governance)

- Governance audit trail (append-only): common.AuditEvent + common.audit.record
  and a superuser-only read-only admin. Wired into privileged actions:
  UserAdmin role/status changes, user adds, user deletes, and ResourceAdmin
  deletions (AGENTS section 6). School admins can never view or edit the
  trail.
- Data retention (privacy): AI_RETENTION_DAYS (0 = disabled, the default) and
  `purge_old_ai_data --days N [--dry-run]`, which deletes only AIInteraction /
  AIGeneration rows older than the window. Budget/cost rows (AIRequestLog)
  are deliberately kept so per-school quotas do not shrink when content is
  forgotten. The command REFUSES to delete anything unless retention is
  enabled or --days is explicit.
- Data-subject export: `export_user_data <username> --out file.json` produces
  a JSON snapshot of one user's AI history and practice attempts; it refuses
  to overwrite an existing file and errors on unknown users.
- Report anonymization guaranteed by test: teacher reports (practice/AI/
  library/teachers) never contain student free-text answers or AI questions.
  (Cross-user 404 for AI interactions/study results and practice attempts was
  already enforced and tested; the owner-only AI-generation view test
  predates this package.)

Gate: ruff 97 (two RUF012 suppressions added on common.AuditEvent Meta with a
rationale comment - Django 5.2's autodetector requires list form); check
clean; 416 tests OK (3 skipped); check --deploy exit 0; pip-audit clean;
migration common.0001 generated, applied from scratch, reversed and re-applied
on the dev DB, makemigrations --check clean.

## Work Package 10 - Ops / CI / deployment (2026-08-24, branch wp/10-ops)

- CI: `.github/workflows/ci.yml` runs the full gate on every push/PR on both
  Ubuntu-22.04 (Python 3.12) and Windows-latest (Python 3.10, the dev target):
  ruff, check (settings_test), makemigrations --check, locale freshness
  (recompiles with Babel and asserts the committed .mo is unchanged), the full
  test suite, `check --deploy` under a production env, and pip-audit.
- Production stack (`deploy/`): docker-compose.prod.yml with PostgreSQL+pgvector
  (pg16), Redis, the web app (gunicorn + Whitenoise + collectstatic on start,
  /healthz/ container healthcheck), the two queue workers (process_documents /
  process_whatsapp --loop), and a Caddy reverse proxy terminating TLS (LAN
  domain via Caddyfile), plus Dockerfile and a .env.prod.example.
- Backup/restore: deploy/backup.sh (pg_dump custom-format + media tar to an
  external drive, nightly systemd timer at Africa/Douala) and deploy/restore.sh
  (destructive drill: stop app, drop+recreate DB, pg_restore + media restore,
  bring the stack back with a /healthz/ pass criterion). The restore drill is a
  once-per-term MANDATORY exercise (deploy/README.md).
- Contracts held by tests (tests/deploy, +9): compose defines the expected
  services/healthchecks, every compose + .env.prod.example key is consumed by
  config/settings.py (or is a compose/Caddy-only key), DATABASE_URL matches
  dj-database-url, scripts look right (set -eu, pg_dump/pg_restore, BACKUP_DIR),
  CI runs the gate on both runners with both requirement files, and the compiled
  French catalog ships in the repo.

Gate: ruff 97 (no new); check clean; 425 tests OK (3 skipped); check --deploy
exit 0; pip-audit clean; PyYAML added to requirements-dev (stated reason:
deploy-contract test parses YAML) - never in production.

## Work Package 2 - production settings hardening (2026-08-23, branch
wp/2-prod-settings)

- Boot guard: `validate_run_mode` refuses to boot with DEBUG=False while
  SECRET_KEY is the dev default or ALLOWED_HOSTS is empty. Verified by unit
  tests AND two subprocess imports (dev-key and empty-hosts modes both
  raise ImproperlyConfigured, exit 1). The suite keeps DEBUG=True;
  `check --deploy` is a separate step with DEBUG=False + production env
  values (documented in .env.example).
- DEBUG-off security defaults (env-overridable) via `base_security_defaults`:
  SSL redirect, HSTS 31536000 + subdomains + preload, secure session/CSRF
  cookies, CSRF_TRUSTED_ORIGINS, proxy SSL header, nosniff, DENY framing,
  same-origin referrer. check --deploy warnings W004/W008/W012/W016 closed.
- TIME_ZONE=Africa/Douala; date-boundary queries audited: report month start
  is local midnight (converted to UTC) and the AI per-day chart buckets by
  LOCAL day. Tests cross the UTC+1 midnight boundary.
- Rate limiting: atomic cache counter (Redis via REDIS_URL when set, locmem
  otherwise) with DB-count fallback; AI_RATE_LIMIT_USE_CACHE selects the
  path; AI_RATE_LIMIT_EXEMPT_SUPERUSER default False. CACHES explicit.
- Sessions: SESSION_COOKIE_AGE, SESSION_IDLE_SECONDS + common.middleware.
  IdleSessionMiddleware (signs out idle users), env-driven
  SESSION_EXPIRE_AT_BROWSER_CLOSE, and accounts.logout-all ("Sign out of
  all devices" from Profile).
- FILE_UPLOAD_MAX_MEMORY_SIZE / DATA_UPLOAD_MAX_MEMORY_SIZE aligned to
  LIBRARY_MAX_UPLOAD_MB.

Gate: ruff 86 (none from WP2 files); check clean; check --deploy exit 0;
324 tests OK (3 skipped); pip-audit clean.

## Work Package 1 - correctness bugs (2026-08-23, branch wp/1-correctness)

- `fix(library)`: `resource.chapters.none()`; regression test renders every
  `Resource.ResourceType` detail page (5 types previously 500).
- `chore(deps)`: pinned `requirements.txt` (Django 5.2.17, python-dotenv,
  pypdf 6.16.2, psycopg[binary] 3.3.4, dj-database-url 3.1.2, gunicorn
  26.1.0, whitenoise 6.12.0); whitenoise middleware added. pypdf 6 closes
  the baseline GHSA; psycopg needed for the Postgres backend; gunicorn +
  whitenoise are the Linux gunicorn/static stack (Windows-runnable,
  functional only under gunicorn on Linux); dj-database-url replaces the
  hand-rolled parser.
- `refactor(config)`: DATABASES via dj-database-url (`DATABASE_URL`,
  `DATABASE_CONN_MAX_AGE` default 60, `?sslmode=` supported). "PG
  DATABASE_URL boots" proven by a subprocess settings-import test.
- `refactor(config)`: `sys.argv` PASSWORD_HASHERS hack removed.
  `--settings=config.settings_test` is the ONLY supported test command
  (README updated) and the full suite passes under it (308 OK, 3 skipped).
- `fix(ai)+docs`: `QuestionTooLong` validation (no more 5000-char silent
  truncation); WhatsApp reply kept generic (no exception text leaked).
- `feat(common)`: LOGGING (console + rotating 5MB file, LOG_LEVEL from env,
  no request/secret content in the formatter) + `/healthz/` returning
  database and processing-queue health.

Gate: ruff 86 remaining (all paired with later packages); `manage.py check`
clean; `check --deploy` exit 0 (security warnings to close in WP2);
suite 308 OK (3 skipped); pip-audit **green** after pypdf>=6, setuptools
84 and Pillow 12 upgrades.

## Work Package 0 - verification results (2026-08-23)

Every finding in packages 1-3 was reproduced before fixing. Verdict per item:

| Item | Finding | Verdict |
|---|---|---|
| WP1.1 | `Resource.chapters.none()` on non-book detail | CONFIRMED - AttributeError, detail page returns 500 |
| WP1.2 | requirements missing psycopg/dj-database-url/gunicorn/whitenoise | CONFIRMED - hand parser drops `?sslmode=`; CONN_MAX_AGE=0 |
| WP1.3 | argv hasher hack in settings.py | CONFIRMED - present; suite passes under settings_test (303 OK) |
| WP1.4 | dead `_candidate_chunks` import | ALREADY FIXED by baseline ruff sweep |
| WP1.4b | silent 5000-char question truncation | CONFIRMED - 32400->5000 stored |
| WP1.5 | no LOGGING, no /healthz | CONFIRMED - /healthz/ 404; no LOGGING dict in settings |
| WP2.1 | no boot guard | CONFIRMED - imports with dev key + DEBUG=False |
| WP2.2 | security headers off on DEBUG=False | CONFIRMED - framework defaults only; X_FRAME_OPTIONS already DENY by default |
| WP2.3 | TIME_ZONE=UTC | CONFIRMED - not Africa/Douala |
| WP2.4 | row-count rate limit + superuser exemption | CONFIRMED - no cache.incr; unconditional exemption |
| WP2.5 | no idle middleware / env session age | CONFIRMED - framework defaults |
| WP2.6 | upload memory mismatch | CONFIRMED - 2.5MB vs LIBRARY_MAX_UPLOAD_MB=100 |
| WP3.1 | file-view headers | PARTIAL - nosniff present (middleware default); CSP/CORP/Cache-Control missing |
| WP3.2 | Range/ETag | CONFIRMED - no Accept-Ranges/ETag/Last-Modified |
| WP3.3 | download throttle/cap/watermark | CONFIRMED - none exist |
| WP3.4 | login throttle/lockout | CONFIRMED - 7 failed logins -> 200 each |
| WP3.5 | admin temp-password reset | CONFIRMED - no such flow |

Baseline gate (2026-08-23): ruff 156->86 remaining (71 autofixed in `style: apply ruff`); `manage.py check` clean; `check --deploy` exits 0 with W004/W008/W009/W012/W016 warnings open; test suite `--settings=config.settings_test` 303 OK (3 skipped); **pip-audit red at baseline** - pypdf 5.9.0 (GHSA-jm82-fx9c-mx94, fix 6.13.3) and venv setuptools 63.2.0 (multiple). pypdf pin must move to >=6 in WP1.

## Not started

French/i18n · offline PWA caching · DRF API · RAG eval · backups &
deployment

## Update rule

Every agent updates this file in the same commit as its work: phase, gate
status, defects closed, defects discovered.

---

# Phase history

## Phase 0 — Architecture

Establish:

- repository
- Django project
- architecture
- environment
- documentation
- initial tests

## Phase 1 — Core Platform

Build:

- authentication
- roles
- schools
- classes
- subjects
- students
- teachers
- admin

## Phase 2 — Digital Library

Build:

- resources
- books
- chapters
- sections
- metadata
- upload
- storage
- permissions
- reader

## Phase 3 — Document Processing

Build:

- extraction
- OCR
- chunking
- processing jobs
- status tracking

## Phase 4 — Semantic Search

Build:

- embeddings
- pgvector
- semantic search
- metadata filters

## Phase 5 — AI Librarian

Build:

- Ask AI
- Ask This Book
- Ask This Chapter
- RAG
- citations
- source inspection

## Phase 6 — AI Study Tools

Build:

- summaries
- revision notes
- definitions
- formulae
- practice questions

## Phase 7 — Question Bank

Build:

- question CRUD
- metadata
- Bloom taxonomy
- answers
- marking schemes
- approval workflow

## Phase 8 — Examination Generator

Build:

- exam configuration
- question selection
- AI generation
- validation
- answer key
- marking scheme
- teacher review
- printable output

## Phase 9 — Student Practice

Build:

- quizzes
- scoring
- explanations
- progress
- recommendations

## Phase 10 — WhatsApp

Build:

- webhook
- account linking
- menus
- search
- AI
- notes
- practice

## Phase 11 — PWA

Build:

- installable PWA
- mobile optimization
- caching
- offline-friendly features

## Phase 12 — Analytics

Build:

- library analytics
- AI usage
- practice performance
- popular topics
- teacher activity

---
