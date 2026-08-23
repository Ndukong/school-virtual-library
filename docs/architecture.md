# Architecture

Status: current as of Phase 2 (digital library).

---

## 1. Project Overview

The School Virtual Library is a school-controlled digital learning platform for
secondary-school students and teachers: digital textbooks, semantic/keyword
search, Retrieval-Augmented Generation (RAG), AI tutoring and revision-note
generation, a question bank, examination and marking-scheme generation,
student practice, WhatsApp access, and a responsive web/PWA front end.

This document records the decisions made in Phase 0. It describes the actual
scaffold, not a full system that does not yet exist.

---

## 2. Technology Stack

| Component | Choice | Notes |
|---|---|---|
| Language | Python 3.10 | Installed locally (3.10.6) |
| Web framework | Django 5.2 LTS | Selected because it supports Python 3.10 (Django 6.x requires 3.12+) and has long-term support |
| API layer | Django REST Framework | Deferred to the phase that first exposes an API (not needed in Phase 0) |
| Database (local dev) | SQLite | Zero-setup on Windows; satisfies the "easy to run on Windows" requirement |
| Database (production target) | PostgreSQL + pgvector | Configured via `DATABASE_URL`; pgvector integration arrives with Phase 4 semantic search |
| Background jobs | Celery (planned) | No worker setup in Phase 0; Redis/Celery deferred to document processing (Phase 3+) |
| Cache/broker | Redis (planned) | Not installed locally yet |
| Object storage | Planned | Controlled file access design deferred to Phase 2 |
| Front end | Responsive HTML/CSS/JS + PWA | No front-end work in Phase 0 |

Dependency rules from `AGENTS.md` apply: no unnecessary dependencies, and
AI-provider code stays behind an abstraction layer.

---

## 3. Repository Layout (Phase 0)

```text
config/            Django project package (settings, urls, wsgi, asgi)
common/            Shared app: base models, admin scoping classes, tests
accounts/          Custom user model, roles, permissions, auth views
schools/           School tenant model
classes/           SchoolClass (class/form) model
subjects/          Subject model
students/          Student profile model
teachers/          Teacher profile model
library/           Resources, books, chapters/sections, upload, reader
templates/         Project-level templates (base, login, dashboards)
static/            Project-level static assets (CSS)
docs/              Architecture and future technical documentation
manage.py          Django management entry point
requirements.txt   Python dependencies (pinned ranges)
.env.example       Documented environment template (never commit .env)
README.md          Project overview and operating instructions
AGENTS.md          Agent operating contract
SKILLS.md          Agent skills and operating playbook
```

Only apps with meaningful boundaries exist. Domain apps are created in their
phases rather than all up front.

---

## 4. Configuration Strategy

All environment-sensitive configuration lives in `.env` (loaded with
`python-dotenv`). `dotenv` never overrides variables already present in the
process environment, so production deployments can inject values directly.

Keys used in Phase 0:

```text
DEBUG
SECRET_KEY
ALLOWED_HOSTS
DATABASE_URL        # optional; unset -> SQLite, postgresql://... -> PostgreSQL
```

### Database selection

```python
if DATABASE_URL set:
    ENGINE = django.db.backends.postgresql   # requires PostgreSQL running
else:
    ENGINE = django.db.backends.sqlite3      # default local dev
```

PostgreSQL URLs follow `postgresql://user:password@host:port/dbname`. Parsing
is implemented in `config.settings.parse_postgresql_url` (no extra dependency):
it accepts the legacy `postgres://` scheme, defaults missing host to
`localhost`, rejects unsupported schemes and URLs without a database name,
and is unit-tested in `config/tests.py`.

`SECRET_KEY` has a development-only fallback. `.env` must set a real value
outside development. `.env` is never committed.

---

## 5. App Boundaries

Planned applications (from `README.md`) and the phase in which each gets a
meaningful boundary:

| App | Purpose | Phase |
|---|---|---|
| `common` | Shared utilities, base models, admin scoping | 0 (created) |
| `accounts` | Authentication and role model | 1 (created) |
| `schools`, `classes`, `subjects`, `students`, `teachers` | Core domain structure | 1 (created) |
| `library` | Resources, books, chapters, sections, metadata | 2 (created; upload/reader live here) |
| `documents` | Extraction pipeline, chunks, processing jobs | 3 |
| `search` | Keyword + semantic search (pgvector) | 4 |
| `ai` | AI provider abstraction and RAG orchestration | 4/5 |
| `question_bank` | Question CRUD, Bloom, marking schemes | 7 |
| `examinations` | Exam generation and validation | 8 |
| `learning` | Student practice and progress | 9 |
| `whatsapp` | Webhook and message handling (thin layer) | 10 |
| `notifications` | User notifications | 12 |
| `reports` | Analytics and reporting | 12 |

Apps are added as their phase starts. The exact set may evolve with
architectural justification.

---

## 5.1 Phase 1 Design Decisions

These decisions were deferred from Phase 0 and are now fixed:

### Custom user model
`AUTH_USER_MODEL = "accounts.User"` extends Django's `AbstractUser` with a
`role` field and a nullable `school` foreign key. It was set before any real
migrations existed. Changing it later would require a full database rebuild,
so this is now permanent.

### Role model
Roles are mutually exclusive (ADMIN / TEACHER / STUDENT), implemented as a
single `role` field with the least-privileged default (`STUDENT`). All role
decisions flow through centralized helpers in `accounts/permissions.py`
(`is_admin`, `is_teacher`, `is_student`) and class-based mixins
(`AdminRequiredMixin`, `TeacherRequiredMixin`, `StudentRequiredMixin`);
views never hand-roll role checks. Superusers count as administrators only —
never as teachers or students. Django groups remain available for future
fine-grained permissions but are not used for primary roles.

### Profiles vs. auth users
`Student` and `Teacher` are separate one-to-one profile models; the user
model handles authentication only. Profiles enforce invariants in both
`clean()` and `save()`:

- profile role must match the linked user's role,
- profile school must match the linked user's school,
- a student's class must belong to their school,
- a teacher's subjects must belong to their school.

Save-time enforcement exists because admin inlines assign the user link after
form validation.

### Multi-tenancy isolation (school scoping)
Every school-scoped object carries a `school` foreign key with uniqueness
scoped per school (class names, subject names/codes, admission numbers,
staff numbers). In the admin:

- non-superuser administrators see only their own school's objects
  (`SchoolScopedModelAdmin.get_queryset`),
- saves by non-superusers force `school` to the administrator's own school,
- inline FK/M2M choices are restricted to the administrator's own school
  (`SchoolRestrictedInlineMixin`),
- school administrators can never grant `is_staff`/`is_superuser` or edit
  groups through `UserAdmin`,
- `School` records themselves are platform-superuser-only
  (`PlatformOnlyModelAdmin`).

### Bootstrap workflow
A school is onboarded via
`python manage.py create_school_admin --school "Name" --username ...`
which creates/reuses the school and attaches an administrator (password
validated against Django's validators; prompted securely when omitted).

### Test performance
Test runs use MD5 password hashing (`manage.py test` only). Production
password hashing is unaffected.

---

## 5.2 Phase 2 Design Decisions (Digital Library)

### App boundary
`library` owns resources, metadata, upload, storage, and the reader. The
`documents` app (extraction, chunking, jobs) starts in Phase 3 when it has a
meaningful boundary; `Resource.processing_status` already carries the full
state machine from `AGENTS.md` section 11 so no migration churn follows.

### Uploads are untrusted input
Phase 2 accepts **PDF files only** (matches the textbook/past-paper focus and
the Phase 3 PDF/OCR pipeline). Validation lives in
`library.services.validate_upload`: extension whitelist, size cap
(`LIBRARY_MAX_UPLOAD_MB`, default 100), and an actual `%PDF-` signature check
on file content — client-supplied content types are never trusted.
`sanitize_original_filename` strips path components and unsafe characters;
it is display metadata only and never constructs filesystem paths. Storage
paths are generated exclusively by Django's FileField/storage stack under
`MEDIA_ROOT/resources/<year>/<month>/`.

### Private storage, controlled access
Media is deliberately not routed in the URLconf: there is no direct
`/media/` serving. Files stream through permission-checked views
(`library-download`, `library-read`) using `FileResponse`. Read rules are
centralized in `library.services.user_can_read_resource` /
`visible_resources`:

- platform superusers: everything,
- school administrators: everything in their school (including inactive),
- teachers: everything in their school,
- students: active resources with the SCHOOL access policy only.

Views derive objects from the visible queryset, so unauthorized or
cross-school IDs yield 404 rather than leaking existence.

### Metadata and licensing
Resources carry the full metadata set required by AGENTS.md section 10
(author, publisher, edition, ISBN, curriculum, language, publication year,
subject/class links) plus licensing status (OWNED / LICENSED / OPEN_ACCESS /
PUBLIC_DOMAIN / TEACHER_CREATED / SCHOOL_CREATED / UNKNOWN), access policy
(SCHOOL / TEACHERS_ONLY), uploader attribution, and an `is_active` flag for
takedowns. Books require an attached file. Subject/class links must belong to
the resource's school; replacing a file resets processing to UPLOADED.

### Structure for future RAG
Books carry `BookChapter` and `BookSection` rows with page ranges so Phase 3
extraction and Phase 5 citations can anchor to the right location. URLs use
the resource's UUID (`public_id`); integer pks stay internal.

---

## 6. Security Baseline

Security-relevant choices already made in Phase 0:

- Secrets via `.env`; never committed.
- `ALLOWED_HOSTS` restricts host headers.
- `SECRET_KEY` is environment-driven (dev-only fallback).
- Django security middleware (SecurityMiddleware, CSRF, X-Frame-Options) enabled.
- Static root and media root separated; uploaded documents will be served only
  through controlled views in later phases, never directly.

Security hardening topics tracked in `AGENTS.md`: authentication,
authorization, CSRF, XSS, SQL injection, file-upload attacks, path traversal,
insecure direct object references, API abuse, webhook spoofing, and rate
limiting. These are addressed in the phases as each feature appears.

---

## 7. Phase Roadmap

Referenced from `README.md` section 8. Phase 0 is complete.

```text
0  Architecture and project foundation   [THIS PHASE]
1  Core platform (auth, roles, schools)
2  Digital library
3  Document processing
4  Semantic search
5  AI librarian (RAG)
6  AI study tools
7  Question bank
8  Examination generator
9  Student practice
10 WhatsApp
11 PWA
12 Analytics
```

Each completed phase ends with a git checkpoint and a Phase Completion Report
per `AGENTS.md` section 6.

---

## 8. Explicit Non-Goals for Phase 0

- No domain models or migrations beyond Django's defaults.
- No PostgreSQL/pgvector setup (SQLite runs local development now).
- No Redis/Celery worker (deferred to document processing).
- No DRF wiring (deferred to the first API phase).
- No front-end, PWA, WhatsApp, or AI provider configuration.
- No authentication or role model (Phase 1).

---

## 9. Verification

Phase 0 verification commands:

```text
.venv\Scripts\python.exe manage.py check
.venv\Scripts\python.exe manage.py test
```

Both must pass before the phase is considered complete.

---

## 10. Open Questions / Future Decisions

- Object storage provider (`STORAGE_PROVIDER`) for large documents: Phase 3
  (local MEDIA storage is sufficient until then).
- AI provider of record (`AI_PROVIDER`) and models: Phase 4.
- Celery vs. alternative background job system: Phase 3.
- Additional upload formats (DOCX, images, EPUB): when their extraction
  pipelines exist; PDF-only is a deliberate Phase 2 constraint.
- Self-service admin views beyond Django admin (school dashboards): Phase 2+.