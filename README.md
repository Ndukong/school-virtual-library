# School Virtual Library

A school-controlled digital library and AI-assisted learning platform for secondary-school students and teachers.

The platform is designed to make approved school learning resources searchable, readable and usable through:

- Responsive web/PWA
- Android phones
- Windows computers
- WhatsApp
- AI-powered tutoring and document search

## Vision

This is not intended to be merely a PDF repository.

The long-term goal is:

```text
School Resources
      |
      v
Digital Library
      |
      +----> Semantic Search
      |
      +----> AI Tutor
      |
      +----> Revision Notes
      |
      +----> Question Bank
      |
      +----> Examination Generator
      |
      +----> Student Practice
      |
      +----> WhatsApp
      |
      +----> Learning Analytics
```

---

# 1. Main Users

## Administrator

Manages:

- schools
- users
- classes
- subjects
- library resources
- permissions
- AI settings
- WhatsApp
- reports

## Teacher

Can:

- access teaching resources
- upload authorized material
- use AI against selected resources
- create questions
- manage question bank
- generate examinations
- generate marking schemes
- monitor authorized student learning activity

## Student

Can:

- browse permitted resources
- search
- read books
- ask AI questions
- generate revision material where permitted
- practice questions
- view personal progress
- use WhatsApp learning features

---

# 2. Technology

Preferred architecture:

- Python
- Django
- Django REST Framework where appropriate
- PostgreSQL
- pgvector
- Redis
- Celery or equivalent
- Object/file storage
- Configurable AI provider
- Responsive frontend
- PWA
- WhatsApp Business API

The architecture should avoid unnecessary vendor lock-in.

---

# 3. Major Components

```text
accounts/
schools/
students/
teachers/
classes/
subjects/
library/
documents/
search/
ai/
question_bank/
examinations/
learning/
whatsapp/
notifications/
reports/
common/
```

The exact structure may evolve if the lead developer has a strong architectural reason.

---

# 4. Core Features

## Digital Library

Resources may include:

- textbooks
- teacher notes
- revision notes
- past papers
- marking schemes
- practical guides
- school-created resources

Resources are categorized by:

- subject
- class/form
- curriculum
- topic where appropriate
- resource type

## Document Processing

Uploaded documents may go through:

```text
Upload
  ↓
Validation
  ↓
Text extraction
  ↓
OCR if necessary
  ↓
Structure detection
  ↓
Chunking
  ↓
Embeddings
  ↓
Search index
  ↓
Ready
```

## AI

The AI should support:

- Ask the library
- Ask this book
- Ask this chapter
- Explain a concept
- Summarize
- Generate revision notes
- Generate questions
- Generate examinations
- Generate marking schemes

AI answers grounded in library resources should include source information.

## Question Bank

Questions are tagged with:

- subject
- class
- topic
- subtopic
- question type
- difficulty
- marks
- Bloom level
- source
- answer
- marking scheme

## Examination Generator

Teachers can configure:

- class
- subject
- topics
- marks
- duration
- question types
- difficulty
- Bloom distribution

AI-generated examinations require teacher review before publication.

## WhatsApp

WhatsApp acts as a front-end to the existing backend.

Example:

```text
Student
  ↓
WhatsApp
  ↓
"Explain electromagnetic induction using my Form 5 Physics book."
  ↓
Backend
  ↓
RAG
  ↓
AI
  ↓
WhatsApp response
```

## PWA

Students should be able to access the system from Android browsers and install it as a PWA.

---

# 5. RAG Architecture

The intended retrieval flow is:

```text
Question
  ↓
Determine scope
  ↓
Permission filtering
  ↓
Semantic/keyword search
  ↓
Retrieve chunks
  ↓
Rank
  ↓
Build context
  ↓
AI
  ↓
Answer + sources
```

The AI must not fabricate sources or page numbers.

If the selected resource does not contain enough information, the system should say so.

---

# 6. Security

Security is a first-class requirement.

The application must implement:

- authentication
- authorization
- CSRF protection
- secure file access
- input validation
- rate limiting
- webhook verification
- safe file handling
- secret management
- audit logging
- privacy controls

Student data must never be exposed to unauthorized users.

---

# 7. Copyright

Every resource should record licensing/copyright status where practical.

Suggested statuses:

```text
OWNED
LICENSED
OPEN_ACCESS
PUBLIC_DOMAIN
TEACHER_CREATED
SCHOOL_CREATED
UNKNOWN
```

Do not build workflows that encourage unauthorized distribution of commercial textbooks.

---

# 8. Development Phases

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

# 9. AI Development Workflow

The primary development model is DeepSeek V4 Flash.

The secondary independent reviewer is Big Pickle.

Do not have both agents editing simultaneously.

Preferred workflow:

```text
DeepSeek
  ↓
Implement phase
  ↓
Test
  ↓
Commit
  ↓
Big Pickle
  ↓
Review
  ↓
Report
  ↓
DeepSeek
  ↓
Fix
  ↓
Test
  ↓
Commit
```

Other free-tier models available through OmniRoute can be used for:

- simple CRUD
- CSS
- documentation
- test generation
- small refactors
- second opinions
- low-risk tasks

---

# 10. Development Commands

Typical commands:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

python manage.py migrate
python manage.py createsuperuser
python manage.py check
python manage.py test
python manage.py runserver
```

If the project uses `pyproject.toml`, Docker, or another dependency system, follow the repository's actual configuration.

For background processing, document the exact commands for Redis/Celery once implemented.

---

# 11. Environment Configuration

Use `.env` for secrets.

Never commit `.env`.

Provide `.env.example`.

Expected configuration may include:

```text
DEBUG=
SECRET_KEY=
DATABASE_URL=

AI_PROVIDER=
AI_API_KEY=
AI_MODEL=
EMBEDDING_MODEL=

REDIS_URL=

STORAGE_PROVIDER=
STORAGE_BUCKET=
STORAGE_ACCESS_KEY=
STORAGE_SECRET_KEY=

WHATSAPP_PROVIDER=
WHATSAPP_ACCESS_TOKEN=
WHATSAPP_PHONE_NUMBER_ID=
WHATSAPP_VERIFY_TOKEN=
```

Do not assume every variable is needed in every phase.

---

# 12. Testing

Every phase should add appropriate tests.

Before a phase is considered complete:

```bash
python manage.py check
python manage.py test
```

Also test the actual user workflow where possible.

---

# 13. Documentation

Keep documentation current.

At minimum:

```text
README.md
AGENTS.md
SKILLS.md
.env.example
```

Additional documentation may include:

```text
docs/
  architecture.md
  database.md
  rag.md
  ai.md
  deployment.md
  whatsapp.md
  security.md
```

---

# 14. Definition of Done

A feature is complete only when:

- implementation exists
- database migrations are correct
- relevant tests pass
- permissions are tested
- errors are handled
- documentation is updated
- secrets are protected
- critical security issues are resolved
- the intended UI workflow works

---

# 15. Current Development Rule

Before implementing anything:

1. Read `AGENTS.md`.
2. Read `SKILLS.md`.
3. Inspect the repository.
4. Determine the current phase.
5. Review Git history.
6. Understand existing architecture.
7. Plan the change.
8. Implement the smallest coherent change.
9. Test.
10. Document.
11. Commit.

Do not build all phases at once.

---

# 16. Current Project Status

**Phase 0 — Architecture and project foundation: COMPLETE.**

Established:

- Git repository with `.gitignore`
- Django 5.2 LTS project (`config/`) and `common/` app
- Env-driven settings via `.env` / `.env.example` (SQLite local, PostgreSQL-ready via `DATABASE_URL`)
- `docs/architecture.md` recording Phase 0 decisions
- Initial configuration smoke tests (`python manage.py test`)

**Phase 1 — Core Platform: COMPLETE.**

Established:

- Custom user model (`accounts.User`) with roles (Administrator / Teacher / Student) and school scoping
- Schools, classes, subjects, student profiles, teacher profiles with per-school uniqueness constraints
- Centralized permission helpers and role-gated dashboards (login/logout, role routing)
- School-isolated Django admin: non-superuser admins see and manage only their own school; privilege escalation blocked
- `create_school_admin` management command for onboarding schools
- 72 tests covering models, permissions (allow/deny), auth flows, admin scoping, and the command

**Phase 2 — Digital Library: COMPLETE.**

Established:

- `Resource` model with full metadata (author/publisher/ISBN/curriculum/...),
  licensing status, access policy (whole school / teachers only), uploader
  attribution, and the document-processing state machine (pipeline lands in Phase 3)
- Books with chapters and sections (page ranges ready for future RAG citations)
- Secure upload flow for staff: PDF-only (extension + size + `%PDF` signature
  checks), filename sanitization, school-forced storage paths
- Private media: no direct `/media/` serving; controlled download and inline
  read views enforce per-role access (students see whole-school resources only)
- Library list with search/type filters and pagination; mobile-first detail
  page with Read/Download actions
- 32 additional tests (104 total): access matrix, IDOR/cross-school denials,
  upload security incl. disguised-content rejection, pagination safety

**Phase 3 — Document Processing: COMPLETE.**

Established:

- Database-backed job queue (`ProcessingJob`) with atomic claiming, retries,
  and per-step deduplication - runs without Redis; worker:
  `python manage.py process_documents` (`--loop`, `--resource-id`)
- PDF text extraction via pypdf with page boundaries preserved
  (`ExtractedPage`), single-page fault tolerance
- Honest scanned-page handling: missing text layers logged as warnings;
  fully-scanned documents FAIL with "OCR required" instead of faking success
- Chunking (`DocumentChunk`) with size/overlap settings, page anchors, and
  chapter/section mapping for future citations
- Full diagnostics: `ProcessingLog` (INFO/WARNING/ERROR) surfaced in admin;
  failures marked on the resource immediately
- Idempotent re-runs (replace strategy) and reprocess command per resource

**Phase 4 — Semantic Search: COMPLETE.**

Established:

- AI provider abstraction (`ai` app): `mock` (offline deterministic vectors),
  `openai_compatible` (NVIDIA NIM / routers / vLLM via `AI_BASE_URL`),
  `gemini` - all with timeout, retries, and full usage logging
  (`AIRequestLog`); keys only via `.env`, nothing hard-coded
- EMBED step chained into the processing pipeline (CHUNK -> EMBED -> READY)
  with model-tagged vectors; changing `AI_EMBEDDING_MODEL` re-embeds once
- Hybrid search: keyword term-ranking fused with semantic cosine ranking
  (Reciprocal Rank Fusion); graceful keyword-only degradation on provider failure
- Permission-first retrieval: school scoping + access policies applied BEFORE
  ranking; scope filters for subject / class / resource type / single book
- `/search/` results page with snippets, page badges, filters, and header nav

To enable real embeddings locally:

```bash
# .env (never committed)
AI_PROVIDER=openai_compatible
AI_BASE_URL=https://integrate.api.nvidia.com/v1   # NVIDIA NIM example
AI_API_KEY=nvapi-...
AI_EMBEDDING_MODEL=nvidia/nv-embedqa-e5-v5
```

Then re-run pipelines: `python manage.py process_documents --resource-id <uuid>`
(or re-upload). Groq has no embeddings endpoint - reserve it for Phase 5 chat.

**Phase 5 — AI Librarian: COMPLETE.**

Established:

- RAG question answering grounded in the school library: Ask (whole library),
  Ask This Book, Ask This Chapter - retrieval is always permission-filtered first
- Groq as default chat provider (`AI_CHAT_PROVIDER=groq`); Gemini and NVIDIA
  NIM selectable as backups via env; offline `mock` for tests
- Versioned, injection-resistant system prompt: retrieved text is DATA not
  instructions; citations `[n]` must match provided sources; invented
  pages/quotes forbidden; insufficient material answered honestly WITHOUT
  calling the model
- Citation validation + sanitizing; answer page shows Sources Used with links,
  pages, and chapter names (source inspection)
- Per-user rate limiting, provider-outage fallback messaging, full audit via
  `AIInteraction`; answers are owner-only (404 cross-user)

To enable the real chat provider:

```bash
# .env
AI_CHAT_PROVIDER=groq
AI_API_KEY=gsk-...
# optional: AI_CHAT_MODEL=llama-3.1-8b-instant
```

Development commands:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

python manage.py migrate
python manage.py createsuperuser        # platform superuser
python manage.py create_school_admin --school "Name" --username admin1
python manage.py process_documents      # drain processing queue (or --loop)
python manage.py check
python manage.py test
python manage.py runserver
```

**Recommended next step: Phase 6 — AI Study Tools** (summaries, revision
notes, definitions/formulae, practice-question generation from selected
material).

**Phase 6 — AI Study Tools: COMPLETE.**

Established:

- Study tool suite: Summary, Revision notes, Definitions & formulae,
  Practice questions - all generated FROM retrieved school material with
  [n] citations and the same injection-resistant versioned prompts
- No focus topic => the scope's chunks are used directly in document order
  ("summarize this book" means this book); with a topic, ranked hybrid search runs
- Zero-material requests answered honestly without spending provider tokens
- Outputs saved as owner-only `AIGeneration` records ("My materials" list),
  persistently labeled "AI-generated study support - verify with your teacher"
- Shared rate limiter across Ask + Generate (`ai/ratelimit.py`)

Entry points: `/ai/study/`, per-book "Study tools" button on resource pages,
cross-links from the AI Tutor ask page.

---

# 17. Long-Term Vision

The finished system should provide a unified school learning environment:

```text
                     SCHOOL DIGITAL CAMPUS

                           LIBRARY
                              |
             +----------------+----------------+
             |                |                |
             v                v                v
        Textbooks          Search          Resources
             |
             v
          AI/RAG
             |
      +------+------+----------------+
      |             |                |
      v             v                v
   AI Tutor      Notes          Question Bank
                                      |
                                      v
                                  Examinations
                                      |
                                      v
                                   Practice
                                      |
                                      v
                                  Analytics

Students access through:

             WEB / PWA / ANDROID / WHATSAPP
```

The platform should remain reliable, maintainable and understandable as it grows.
