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
7. Rate limiting counts rows without a lock; concurrent requests slip past.
   (WP2)
8. ~~Silent truncation of user input.~~ **CLOSED in WP1**: questions over
   5000 chars are rejected with a user-facing message, never truncated.

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

OCR · French/i18n · offline PWA caching · pgvector · DRF API · RAG eval ·
backups & deployment

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
