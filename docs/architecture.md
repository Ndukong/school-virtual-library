# Architecture

Status: current as of Phase 6 (AI study tools).

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
documents/         Extraction pipeline, chunks, job queue, worker command
ai/                AI provider abstraction (chat: Groq default; Gemini/NIM
                   backups), usage logging, RAG + study-tool orchestration
search/            Keyword + semantic + hybrid retrieval
question_bank/     Questions, metadata, approval workflow, AI import
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
| `documents` | Extraction pipeline, chunks, processing jobs | 3 (created) |
| `search` | Keyword + semantic search | 4 (created; pgvector swap pending Postgres) |
| `ai` | AI provider abstraction, RAG orchestration, usage logging | 4/5 (created) |
| `question_bank` | Question CRUD, Bloom, marking schemes | 7 (created) |
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

## 5.3 Phase 3 Design Decisions (Document Processing)

### Background jobs without Redis
Redis/Celery are not available on the development machine, so the queue is
database-backed: `ProcessingJob` rows are claimed by workers with an atomic
conditional UPDATE (`status=PENDING -> RUNNING`), which is safe on both
SQLite and PostgreSQL. The worker is
`python manage.py process_documents` (`--loop` for daemon mode, `--resource-id
<uuid>` to re-run one resource). Task logic lives in `documents.services`;
only the dispatcher would change if a Celery deployment appears later.
`DOCUMENTS_INLINE_PROCESSING=True` runs jobs synchronously at upload time for
tests and tiny deployments. Jobs retry up to `DOCUMENTS_MAX_ATTEMPTS`
(default 3); every failure is recorded on the job and in `ProcessingLog`,
and the resource itself shows FAILED immediately (a successful retry
overwrites that).

### Pipeline and status transitions
Upload enqueues EXTRACT then CHUNK (order preserved by creation time).
EXTRACT: VALIDATING -> EXTRACTING -> per-page text via pypdf into
`ExtractedPage` rows. CHUNK: CHUNKING -> `DocumentChunk` rows -> READY.

### Honesty about OCR
Pages whose PDF text layer is empty are stored with `has_text=False` and a
WARNING log names them; OCR itself requires Tesseract and is deliberately not
bundled this phase (`documents.services.ocr_available()` is the integration
point). A document with no extractable text anywhere FAILS with an explicit
"OCR required" error instead of pretending success. Single-page extraction
errors degrade gracefully rather than killing the run.

### Chunking rules
Target size `DOCUMENTS_CHUNK_SIZE` (1200 chars) with `DOCUMENTS_CHUNK_OVERLAP`
(150) overlap; oversized paragraphs split at word boundaries; chunks carry
`page_start/page_end` plus chapter/section links derived from page ranges so
Phase 5 citations can anchor precisely. Re-running any step replaces prior
results transactionally (idempotent). Extraction results live in separate
tables; original files are never modified.

---

## 5.4 Phase 4 Design Decisions (Semantic Search)

### AI provider abstraction
All AI access goes through the `ai` app (`AGENTS.md` section 13). Providers:
`mock` (deterministic offline vectors - tests/dev), `openai_compatible`
(NVIDIA NIM, routers, vLLM via `AI_BASE_URL`), and `gemini`. Groq has no
embeddings endpoint and is reserved for chat generation in Phase 5. Every
call is wrapped with timeout + exponential-backoff retries, and logged to
`AIRequestLog` (provider, model, kind, ok/error, latency, tokens where the
API reports them). Keys live only in `.env`; nothing is hard-coded.

### Embedding pipeline
The processing queue gained an EMBED step chained automatically after CHUNK;
resource status becomes EMBEDDING then READY. `ChunkEmbedding` stores the
vector as JSON alongside `model_name`/`dimensions`; embeddings are generated
once per chunk unless the model changes (stale vectors are deleted and
re-embedded per AGENTS.md section 14).

### Vector storage today vs pgvector
PostgreSQL/pgvector is not installed locally, so vectors live in JSON and
cosine ranking runs in Python over the permission-filtered candidate set -
fine at school-library scale. The search interface in
`search.services.hybrid_search` does not change when pgvector lands: only
the storage/ranking internals swap.

### Permission-first retrieval
Every query starts from chunks whose resource passes `visible_resources`
(school scoping + access policy), then applies scope filters (subject,
class, resource type, single book) and ranks within that set. Unauthorized
content can never leak through similarity.

### Hybrid retrieval
Keyword ranking (term coverage over chunk text) and semantic ranking fuse
via Reciprocal Rank Fusion. Provider outages degrade gracefully to
keyword-only results. Snippets escape HTML and mark matches server-side.

---

## 5.5 Phase 5 Design Decisions (AI Librarian)

### Chat provider: Groq by default, selectable backups
Groq is the default chat provider (`AI_CHAT_PROVIDER=groq`) using its
OpenAI-compatible endpoint; per-provider default models apply unless
`AI_CHAT_MODEL` overrides (`llama-3.3-70b-versatile` for Groq,
`gemini-2.0-flash` for Gemini). Backups are selectable via env only:
`gemini`, `openai_compatible` (NVIDIA NIM / routers), `mock` for offline
tests. The factory fails fast with a clear error when a network provider is
selected without an API key.

### RAG orchestration (`ai/rag.py`)
Question -> permission-filtered hybrid retrieval -> numbered source blocks
wrapped in `<retrieved_documents>` delimiters -> grounded generation ->
citation validation. Grounded scopes (library/subject/class/book/chapter)
answer ONLY from retrieved sources; when retrieval returns nothing the
system answers honestly WITHOUT calling the model - no hallucination surface
and no wasted tokens. General scope skips retrieval entirely.

### Prompt discipline (SKILLS.md sections 8/9/29)
A versioned system prompt (`RAG_PROMPT_VERSION=rag-v1`, recorded on every
interaction) states that retrieved text is DATA not instructions, forbids
inventing pages/quotations/sources, requires [n] citations matching provided
blocks, and mandates an explicit "not enough material" response when sources
are insufficient. Post-generation sanitizing strips citation markers that
reference non-existent blocks.

### Audit, privacy, and abuse control
Every question creates an `AIInteraction` (user, school, scope, question,
answer, model, prompt version, cited chunk ids, retrieved count) used for
audit and school-level analytics later; answer pages are owner-only
(cross-user access yields 404). A per-user rate limit
(`AI_RATE_LIMIT_PER_MINUTE`, default 10) guards API cost; superusers are
exempt. Provider outages produce a friendly recorded answer rather than a
500.

---

## 5.6 Phase 6 Design Decisions (AI Study Tools)

### One engine, four kinds
`ai/study.py` generates Summary / Revision notes / Definitions & formulae /
Practice questions from the SAME grounded pipeline as the AI Librarian:
permission-filtered retrieval -> numbered blocks -> versioned prompt
(`STUDY_PROMPT_VERSION=study-v1`) -> citation validation. Zero retrieval
produces an honest "no material" result WITHOUT calling the provider.
Outputs are stored as `AIGeneration` rows, owner-only viewable.

### Retrieval: topic vs whole-scope
With a focus topic, ranked hybrid search runs as usual. WITHOUT a topic,
"summarize this book" must mean the book itself: the scope's chunks are
taken directly in document order instead of racing a similarity query -
deterministic and true to user intent.

### Human-in-the-loop labeling
Every generated artifact carries a persistent "AI-generated study support -
verify with your teacher" notice; practice questions are explicitly NOT
teacher-approved and never enter the question bank (Phase 7 owns approval
workflow). Rate limiting is shared across ask + generate via `ai/ratelimit`
so neither feature can bypass the cap.

---

## 5.7 Phase 7 Design Decisions (Question Bank)

### Staff-only by design
The whole `/questions/` area requires teacher/admin roles: answer keys must
never reach student accounts. Students receive practice through Phase 9,
which serves questions without answers until submission.

### Approval workflow
DRAFT -> PENDING_REVIEW -> APPROVED / REJECTED; approve is allowed from DRAFT
or PENDING (small schools may have a single teacher), never directly from
REJECTED. Editing any content field (body/options/answer/marks/type/
difficulty/Bloom/topic) automatically resets status to DRAFT and clears
approval metadata - an approved question can never silently change. The exam
generator's single sanctioned source is `questions_for_exam(school, ...)`,
which returns APPROVED + active + school-scoped rows only.

### AI import with human gate
`import_from_ai_generation` parses Q:/A: blocks from PRACTICE_QUESTIONS
generations (tolerant parser; malformed blocks counted and skipped), creates
questions as PENDING_REVIEW with full traceability (`ai_generation` FK +
source resource/chapter inheritance), and is restricted to the generation's
owner. Nothing auto-approves.

### Bloom and duplicates
Bloom level is editable metadata (SKILLS.md section 12), not gospel. Duplicate
groundwork compares whitespace/punctuation-normalized bodies within a school;
embedding-based similarity is deferred until it earns its complexity.

### Validation layering
Model `clean()` enforces cross-field rules on EVERY save (marks range 1-100,
MCQ needs >=2 options, TF options fixed, subject/class/source school match)
because Django validators only run in form validation - programmatic saves
must not bypass integrity.

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

- Object storage provider (`STORAGE_PROVIDER`) for large documents: when
  production deployment nears (local MEDIA storage is sufficient for now).
- PostgreSQL/pgvector deployment for production-scale vector ranking
  (current JSON+Python approach is the documented fallback).
- OCR engine deployment (Tesseract binary) for scanned textbooks: required
  before the AI Librarian can answer questions from scanned books.
- Embedding model of record for production (NVIDIA NIM vs Gemini embeddings);
  model switches trigger automatic re-embedding.
- Streaming responses and async question queue if LLM latency hurts UX.
- Additional upload formats (DOCX, images, EPUB): when their extraction
  pipelines exist; PDF-only is a deliberate constraint.
- Self-service admin views beyond Django admin (school dashboards): later.