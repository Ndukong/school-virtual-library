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

1. `library/views.py` - `Resource.chapters.none()` should be
   `resource.chapters.none()`. Non-book resource detail pages crash.
2. `requirements.txt` is missing psycopg; the PostgreSQL path cannot boot.
3. `search/services.py` - keyword ranking slices an id-ordered queryset,
   silently dropping matches in later resources.
4. `search/services.py` - every embedding is loaded into memory per query.
5. `whatsapp/views.py` - retrieval and LLM work runs inside the webhook,
   and exception text is sent to users.
6. No LOGGING config, no health endpoint, no CI.
7. Rate limiting counts rows without a lock; concurrent requests slip past.

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
