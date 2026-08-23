# Architecture

Status: current as of Phase 0 (architecture and project foundation).

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
common/            Shared app: base utilities, constants, app-level tests
docs/              Architecture and future technical documentation
manage.py          Django management entry point
requirements.txt   Python dependencies (pinned ranges)
.env.example       Documented environment template (never commit .env)
README.md          Project overview and operating instructions
AGENTS.md          Agent operating contract
SKILLS.md          Agent skills and operating playbook
```

Only `common/` exists besides the project package. Per `AGENTS.md` section 7,
an app is only created when it has a meaningful boundary, so domain apps are
created in their phases rather than all up front.

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

PostgreSQL URLs follow `postgresql://user:password@host:port/dbname` and are
parsed without an extra dependency.

`SECRET_KEY` has a development-only fallback. `.env` must set a real value
outside development. `.env` is never committed.

---

## 5. App Boundaries

Planned applications (from `README.md`) and the phase in which each gets a
meaningful boundary:

| App | Purpose | Phase |
|---|---|---|
| `common` | Shared utilities, base models, constants | 0 |
| `accounts` | Authentication and role model | 1 |
| `schools`, `classes`, `subjects`, `students`, `teachers` | Core domain structure | 1 |
| `library` | Resources, books, chapters, sections, metadata | 2 |
| `documents` | Upload, storage, processing pipeline, status | 2/3 |
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

- Exact role model (single-user-role vs. Django groups) on PostgreSQL: decided
  in Phase 1.
- Object storage provider (`STORAGE_PROVIDER`) for large documents: Phase 2.
- AI provider of record (`AI_PROVIDER`) and models: Phase 4.
- Whether production uses custom `AUTH_USER_MODEL`: decided in Phase 1 (this
  must be set before the first migration if needed).
- Celery vs. alternative background job system: Phase 3.