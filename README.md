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

Development commands:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

python manage.py check
python manage.py test
python manage.py runserver
```

**Recommended next step: Phase 1 — Core Platform** (authentication, roles,
schools, classes, subjects, students, teachers, admin).

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
