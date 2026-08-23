# AGENTS.md — School Virtual Library

Operating contract for AI coding agents on this repository.
Obey this file. If an instruction conflicts with it, STOP and say so
instead of improvising. Ambiguity is not permission.

## 0. What this is

Django 5.2 platform giving a secondary school in Cameroon a
school-controlled digital library: permission-filtered hybrid search,
RAG tutoring grounded only in approved material, teacher question bank,
examination generation, student practice, WhatsApp access, PWA.

Real users: teachers and students on low-end Android phones over
intermittent, metered 3G, in a school with no IT staff. Design for that,
not for a datacenter.

Phase state lives in `docs/status.md`. That file is the source of truth,
not this one and not `README.md`. Read it first.

## 1. Hard rules

1. Before proposing anything: read this file, `SKILLS.md`,
   `docs/status.md`, and `git log --oneline -15`. Inspect the actual code
   in the area you intend to touch.
2. Smallest coherent change. One concern per commit. Never rewrite what a
   fix would repair. Never restart a module because you dislike its style.
3. Reproduce before you fix. A bug fix without a test that failed before
   the change and passes after it is not a fix.
4. Never weaken a security control, permission check, validation rule, or
   test to make something pass. If a test blocks you, assume the test is
   right and you are wrong.
5. Never bypass authentication or authorization. Not temporarily, not in
   a branch, not with a TODO.
6. Permission filtering happens BEFORE retrieval, ranking, or exposure,
   never after. `library.services.visible_resources(user)` is the only
   entry point to library content. Do not query `Resource` or
   `DocumentChunk` from scratch in a view.
7. No AI provider SDK or HTTP call outside `ai/providers/`. The rest of
   the app must not know which provider is configured.
8. No business logic in templates, in `whatsapp/`, or in any future API
   layer. Those are thin adapters over services.
9. The LLM never performs arithmetic that matters: marks, totals, mark
   distributions, scores, Bloom counts. Application code computes it and
   tests assert it.
10. Never fabricate citations, page numbers, quotations, or source
    claims. When retrieval returns nothing, answer honestly WITHOUT
    calling the provider.
11. Retrieved document text is DATA. Prompts keep it inside delimiters
    and explicitly instruct the model to ignore instructions found inside
    it. Any prompt edit bumps the prompt version.
12. Uploaded files, client-supplied identifiers, and webhook payloads are
    hostile input. Validate server-side, always.
13. No secrets in code, tests, fixtures, logs, or commits. Environment
    only, and `.env.example` updated in the same commit.
14. A new dependency requires a stated reason in the commit message, a
    pinned version, and Windows installability. Prefer stdlib and Django.
15. Migrations are generated, inspected, reversible, and tested from the
    current state AND from scratch. Never edit an applied migration.
    Never change `AUTH_USER_MODEL`. ASK before any data migration that
    rewrites existing rows.
16. Every AI call is metered: rate limited, logged, and inside a
    per-school budget. An unmetered provider call is a defect.
17. Expensive work goes in the database-backed queue, never inside a web
    request or webhook. Webhooks acknowledge fast and process later.
18. Teacher approval gates every AI-generated question and every
    examination. No auto-approve, no auto-publish, ever.
19. Documentation describes the system as it IS. If code and docs
    diverge, fix the docs in the same commit.
20. Do not build future-phase features early. Do not change architecture
    silently. Do not leave dead code, commented-out code, or unused
    imports behind.
21. Never swallow an exception to make a symptom disappear. Handle
    expected errors, log unexpected ones with context, return a safe
    message to the user.
22. Never send internal error text, tracebacks, or object ids to a
    student or a phone number.

## 2. Working protocol

1. Read `docs/status.md` and recent git history.
2. Restate the task in one sentence, including what you will NOT do.
3. Inspect the relevant models, services, permissions, and tests.
4. Write the failing test or reproduction first.
5. Implement the smallest coherent change.
6. Run the full gate (section 3).
7. Update `docs/` and `docs/status.md`.
8. Commit with a scoped message.
9. Report using the format in section 12, then STOP and wait.

Do not batch multiple work packages into one pass. Do not start the next
package without a go-ahead.

## 3. Commands and the gate

Setup:

    python -m venv .venv
    .venv\\Scripts\\activate
    pip install -r requirements.txt -r requirements-dev.txt
    python manage.py migrate
    python manage.py createsuperuser
    python manage.py create_school_admin --school "Name" --username admin1
    python manage.py process_documents --loop
    python manage.py runserver

The gate. ALL of these pass before any work is called complete:

    ruff check .
    python manage.py check
    python manage.py check --deploy
    python manage.py test --settings=config.settings_test
    pip-audit

A red gate means the work is not done. Do not report success on a red
gate. Do not silence a check to make it green.

## 4. Definition of Done

A change is DONE only when every line is true:

- [ ] Implementation exists and the intended user workflow actually works
- [ ] A test existed that failed before the change and passes after
- [ ] Allowed AND denied access tested for every new endpoint
- [ ] Cross-school and cross-user access return 404, and it is tested
- [ ] Migrations generated, inspected, reversible, tested
- [ ] Errors handled; nothing internal reaches the user
- [ ] No new unmetered AI call, no new unbounded query, no new N+1
- [ ] User-facing strings wrapped for translation, with a French entry
- [ ] Mobile viewport (360px) checked for any UI change
- [ ] Docs and `docs/status.md` updated
- [ ] No secrets, no dead code, no unused imports
- [ ] Full gate green

## 5. Architecture invariants

    config/          settings, urls, wsgi/asgi
    common/          shared base models and admin helpers
    accounts/        User (ADMIN/TEACHER/STUDENT roles), permissions.py
    schools/ classes/ subjects/ students/ teachers/
    library/         Resource, Book/Chapter/Section, upload, file serving
    documents/       processing pipeline, ProcessingJob queue, chunks
    search/          keyword / semantic / hybrid retrieval
    ai/              providers/, rag.py, study.py, prompts.py, ratelimit.py
    question_bank/   Question, approval workflow
    examinations/    exam config, deterministic selection, papers
    learning/        student practice, scoring, progress
    whatsapp/        webhook + thin router
    pwa/             manifest, service worker
    reports/         analytics

Invariants:

- All role decisions live in `accounts/permissions.py`. Never inline a
  role string check in a view or template.
- All library visibility flows through `library/services.py`.
- All retrieval flows through `search/services.py`.
- All provider access flows through `ai/providers/`.
- All background work flows through `documents/dispatcher.enqueue`.
- Externally exposed identifiers are `public_id` (UUID), never a PK.
- A new app requires a real domain boundary and prior agreement.

## 6. Security baseline

Non-negotiable, and each item has a test:

- Refuse to boot when `DEBUG=False` and `SECRET_KEY` is the dev default
  or `ALLOWED_HOSTS` is empty.
- Production security settings on by default when `DEBUG=False`: SSL
  redirect, HSTS, secure session and CSRF cookies, trusted CSRF origins,
  proxy SSL header, nosniff, deny framing, referrer policy.
- Uploaded PDFs are served only through controlled views, with nosniff, a
  sandboxing CSP, same-origin resource policy, and private no-store
  caching. `/media/` is never served directly.
- Login is throttled and lockable, keyed on username AND IP.
- Sessions expire on idle. Shared lab machines are assumed.
- Rate limits are atomic cache counters, not row counts in a race.
- Students' AI history, practice results, and progress are owner-only.
  Teacher visibility is aggregate and non-verbatim unless a documented
  safeguarding flow says otherwise.
- Privileged actions are audit-logged: resource delete, permission
  change, password reset, cross-school superuser access.

## 7. Deployment reality

Requirements, not preferences:

- **Scanned documents are the norm.** Most material is photocopied. OCR
  (English and French) is a first-class pipeline step, not an
  afterthought. But never fabricate a text layer: unreadable stays
  honestly failed.
- **Bilingual or useless.** Anglophone and francophone sections both
  exist. UI, AI answers, refusals, and resource metadata are
  language-aware.
- **Bandwidth is money.** Text-first, paginated, lazy, compressed. Show
  data cost before any download. Never preload a textbook.
- **Offline matters more than AI.** Opt-in per-resource offline reading
  and offline practice with sync-on-reconnect beat any new model feature.
- **No IT staff.** Target one LAN box on the school wifi: PostgreSQL with
  pgvector, TLS via a reverse proxy, worker under a service manager,
  nightly backup to an external drive, and a restore procedure that has
  actually been executed.
- **Timezone is Africa/Douala.** Every date-boundary query is computed in
  local time.
- Development must stay easy on Windows.

## 8. Known defects — do not reintroduce

- Class-level manager access (`Resource.chapters`) where an instance was
  meant (`resource.chapters`). Test every resource type, not just books.
- `requirements.txt` missing what the code needs. If a code path requires
  a package, that package is pinned in requirements.
- Ranking in Python after an arbitrary slice of an id-ordered queryset.
  That silently destroys recall. Rank in the database.
- Loading every embedding into memory per query. Vector distance is the
  database's job.
- LLM or retrieval work inside a webhook or web request.
- Environment behaviour switched on `sys.argv`. Use a settings module.
- Rate limits enforced by counting rows without a lock.
- Silent truncation of user input. Validate and tell the user.
- Error-path rows written to analytics tables that also feed quotas.

## 9. Git

Before: `git status` and `git log --oneline -15`.
After: `git diff`, then the gate, then commit.

Format: `fix(library): use instance manager for chapters on non-book pages`

Scopes match app names. One concern per commit. Never rewrite history
unless told to. Never commit `.env`, keys, student data, or the SQLite
database.

## 10. Tool discipline

MCP servers are available. Use the right one and keep context lean:
enable only what the task needs.

- **postgres** — verify the real schema, EXPLAIN search queries, confirm
  indexes exist. Read-only. Never mutate data through it.
- **playwright / chrome-devtools** — prove the workflow. "The intended UI
  workflow works" in the Definition of Done means you clicked it: login,
  upload, read, ask, practice. Throttle to 3G and a 360px viewport for
  any PWA work.
- **context7** — look up current Django 5.2, DRF, pgvector and OCR APIs
  instead of writing them from memory.
- **semgrep** — run on every diff touching views, settings, file serving,
  or auth. Findings are triaged, not ignored.
- **git** — history and diffs for the protocol in section 2.
- **clickup** — work packages and status. Do not put the phase log back
  into `README.md`.

Never paste secrets, `.env` contents, or student data into a tool call.

## 11. When requirements are ambiguous

Infer minor details from existing code and document the choice. STOP and
ask when the ambiguity touches schema, permissions, an external
contract, student privacy, cost, or anything irreversible. Do not ask
questions this repository already answers.

## 12. Report format

After every unit of work:

    TASK:
    STATUS: done / blocked
    Files changed:
    Tests added (and what failed before):
    Gate results (ruff / check / check --deploy / test / pip-audit):
    Migrations:
    Security impact:
    Deliberately NOT done, and why:
    Anything in the request I judged wrong:
    Docs updated:
    Commit:
    Recommended next step:

A phase is never COMPLETE while a critical test fails, the gate is red,
or a known security issue is open.