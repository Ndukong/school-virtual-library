# JSON API v1 (Work Package 11)

Thin, permission-first JSON surface for first-party clients (the PWA and any
future native app). Same security model as the web views, never a bypass:
- Library list starts from `library.services.visible_resources()` (school,
  role and status filtering happen BEFORE serialization).
- Search goes through `search.services` (keyword/semantic/hybrid).
- `POST /api/v1/ask/` uses `ai.rag.ask` → rate limited (`ai.ratelimit`),
  per-school budget metered, prompt-versioned, honest refusals offline.
- Answers are owner-or-404 (superuser may read any).
- Questions are role-filtered exactly like the web (students: APPROVED only;
  teachers/admins: + PENDING_REVIEW, own school).

Auth: session-based like the web. Unauthenticated calls get a JSON `401`,
never a redirect to `/login/`.

| Method | Path                                   | Notes |
|--------|----------------------------------------|-------|
| GET    | `/api/v1/resources/`                   | `?q= &type= &language=en\|fr &page= &page_size=` |
| GET    | `/api/v1/search/`                      | `?q=` (≥2 chars) + filters; snippets included |
| POST   | `/api/v1/ask/`                         | JSON or form `{question, scope, book, chapter}` |
| GET    | `/api/v1/answers/<public_id>/`         | owner or 404 |
| GET    | `/api/v1/questions/`                   | role-filtered, `?subject= &language=` |

Responses are plain JSON with a `page`/`page_size`/`count`/`next`/`previous`
envelope on list endpoints. Errors are `{"error": "..."}` with 400/401/403/
404/429/503. `429` carries the same AI rate-limit message the web shows.

Tests: `api/tests.py` covers unauthenticated 401 (JSON not redirect),
cross-school isolation for resources/search/questions, owner-or-404 answers,
language filters, question role status sets, and the ask rate limit at the
API boundary.

## RAG evaluation harness

`tests/eval/test_golden_set.py` now IMPLEMENTS the scoring (no more skip):

- The corpus is built at test time as `DocumentChunk` rows from the page
  specs in `tests/eval/harness.py` (page numbers map 1:1 onto `expected_pages`).
- A **reference provider** echoes only retrieved sentences that match a
  case's required phrases and refuses instruction-looking sentences, making
  retrieval, citation precision/recall, injection resistance and refusals
  deterministic against the mock provider (no paid model, no network).
- Refusals additionally assert `used_provider=False` and zero provider calls.
- Run: `python manage.py test tests.eval --settings=config.settings_test`
  (already part of the default suite and the CI gate).

Add a case: give it an `id` prefixed `grounded-`, `refusal-`, `injection-`
or `fr-`, add the page text to `tests/eval/harness.py:CORPUS`, cite a real
page, and explain the protected failure mode in `notes`.