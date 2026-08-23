# SKILLS.md — School Virtual Library

Task-triggered playbooks. `AGENTS.md` is what you must always obey; this
file is how to do specific kinds of work here.

Read the playbook whose trigger matches your task. If two match, both
apply. If none match, you are probably doing something this project has
not agreed to: stop and ask.

Mirror each section as an on-demand skill in
`.opencode/skills/<name>/SKILL.md`. Keep them in sync: this file is the
index, those files are what the agent loads mid-task.

| Skill | Trigger |
|---|---|
| test-first | any bug fix or behaviour change |
| phase-gate | before declaring anything complete |
| permissions | any view, endpoint, queryset or template touching content |
| retrieval | search, embeddings, ranking, pgvector |
| rag-grounding | prompts, citations, answers, study tools |
| rag-eval | any prompt or model change |
| document-pipeline | extraction, OCR, chunking, jobs |
| assessment | question bank, exam generation, Bloom, practice |
| file-serving | uploads, downloads, inline reads, storage |
| whatsapp | webhook or messaging changes |
| mobile-pwa | any UI, offline or caching change |
| i18n | any user-facing string |
| ai-cost | anything that calls a provider |
| migration-safety | any model change |
| perf-budget | anything on a hot path |
| debugging | investigating a failure |
| review | reviewing a diff |

---

## test-first

Trigger: any bug fix or behaviour change.

1. Reproduce the problem as an automated test. Watch it fail. Paste the
   failure into your report.
2. Only then write the fix.
3. Watch the same test pass. Run the neighbours for regressions.
4. If you cannot write a failing test, you do not yet understand the bug.
   Keep investigating instead of guessing.

A claim of "fixed" without a before/after test is rejected.

## phase-gate

Trigger: before declaring anything complete.

Run the full gate from `AGENTS.md` section 3, then walk the Definition of
Done line by line and state the result of each line. Not "looks good":
the actual result. If a line is unsatisfied, the status is `blocked`, not
`done`.

Never mark a phase COMPLETE with a red gate, a failing critical test, or
an open security finding.

## permissions

Trigger: any view, endpoint, queryset or template touching content.

- Start every content queryset from `visible_resources(user)`. Never
  filter `Resource` or `DocumentChunk` from scratch in a view.
- Role checks come from `accounts/permissions.py`. Need a new rule? Add
  it there.
- Look up objects by `public_id` scoped to the user's visible set, so a
  wrong id is a 404 and never a leak.
- Privacy over politeness: unauthorized access to someone else's data is
  404, not 403. A 403 confirms the object exists.
- Tests, every time: allowed role, each denied role, anonymous,
  cross-school user, cross-student user, guessed id.

Client-side restrictions are not security controls.

## retrieval

Trigger: search, embeddings, ranking, pgvector.

- Permission filter first, rank second. Always.
- Rank in the database. Never slice an id-ordered queryset and then score
  in Python: it silently drops matches in later resources.
- Vector distance belongs in pgvector with a real index. The Python
  cosine path is a SQLite dev fallback behind the same interface, and
  nothing else.
- Store the model name with every vector. A model change triggers
  re-embedding, never a mixed vector space.
- Prefer a local embedding model: free, offline-capable, bilingual.
- A provider outage degrades to keyword-only. Search never goes down
  because an API did.
- Keep scope keys on an allow-list. Never build a filter from raw input.
- Report p50/p95 latency for any retrieval change.

## rag-grounding

Trigger: prompts, citations, answers, study tools.

- Three separated layers: system instructions, user request, retrieved
  material. Retrieved material is delimited DATA and the prompt says so.
- Cite only blocks actually provided. Validate citation numbers in code
  and strip invalid ones. Never trust the model to behave.
- No retrieval hits means an honest refusal with no provider call.
- Insufficient material means saying what is missing, never filling the
  gap from general knowledge.
- Scoped questions stay in scope. "Ask this book" never silently wanders
  into other books.
- Never attribute a general-knowledge claim to school material.
- Every generated study aid is visibly labelled AI-generated and not
  teacher-verified.
- Bump the prompt version on any prompt edit and record it per
  interaction.

Bad: "According to page 183..." when page 183 was never retrieved.
Good: "The retrieved section on electromagnetic induction explains this
[2]. It does not give a page number."

## rag-eval

Trigger: any prompt, model, chunking or retrieval change.

Run the golden set against the mock provider and report:

- citation precision and recall against expected source pages
- refusal accuracy on out-of-corpus questions (it must refuse)
- injection resistance: a chunk containing "ignore previous
  instructions" must be ignored, with a test proving it
- answer-length and latency drift

A regression in refusal accuracy or injection resistance blocks the
change outright. No prompt edit merges on vibes.

## document-pipeline

Trigger: extraction, OCR, chunking, jobs.

- The original upload is never modified. Extraction output is stored
  separately.
- Assume scanned, mixed, rotated and malformed PDFs. Per-page fault
  tolerance: one bad page does not fail a book.
- OCR runs automatically when a page has no text layer, in English and
  French, as a queue step with per-page progress, resumability, a page
  cap and a timeout. Store confidence; flag low-confidence pages for
  teacher review.
- Failed OCR is reported as failed. Never fabricate a text layer.
- Chunks keep page anchors and chapter/section mapping. Citations depend
  on them.
- Jobs are idempotent, deduplicated per step, retried with a cap, and
  re-runnable. Every step writes a diagnostic log an admin can read.
- Cap chunks per resource and storage per school. One textbook must not
  be able to exhaust the embedding budget.

## assessment

Trigger: question bank, exam generation, Bloom, practice.

- Application code owns all arithmetic: totals, marks, distributions,
  scores. Tests assert the numbers. The LLM never adds up a paper.
- Only approved, active questions reach an examination.
- Editing any content field resets approval. Approved content cannot
  change silently.
- AI questions land in the review queue with source traceability. Never
  approved automatically, never placed directly on a paper.
- Validate every generated question: topic match, class appropriateness,
  difficulty, marks, answer correctness, marking-scheme agreement, Bloom
  plausibility, near-duplicates, unambiguous wording.
- Duplicate detection uses embeddings, not string comparison. "State
  Newton's second law" and "State the second law of Newton" are the same
  question.
- Bloom levels are editable metadata. Report actual versus requested
  distribution instead of pretending they match.
- Answers, model answers, marking schemes and explanations are withheld
  until submission. Re-submission is blocked. Per-student variants use
  seeded shuffling with a version hash printed on the paper.
- Shortfalls are honest errors, never a quietly shorter exam.

## file-serving

Trigger: uploads, downloads, inline reads, storage.

- Validate extension, size and content signature. Reject disguised
  content. Sanitize filenames; never build a path from user input.
- Storage paths are forced by the server and never exposed.
- Every read goes through a controlled view with the security headers in
  `AGENTS.md` section 6, and is logged as an access event.
- Support range requests and ETag so a 100MB PDF is not refetched on
  every seek. Behind a flag, hand off to the web server rather than
  streaming from Django in production.
- Throttle downloads per user with a daily cap; alert on anomalies.
- Watermark inline reads of licensed and owned material with the reader's
  name and timestamp.
- Tests: IDOR, cross-school, wrong role, guessed id, oversized upload,
  disguised file, path traversal.

## whatsapp

Trigger: webhook or messaging changes.

- Verify the signature over the raw body before parsing anything. Fail
  closed when the secret is missing outside DEBUG.
- Acknowledge fast: persist the inbound message, return, then process in
  the queue and send the reply. No retrieval or LLM work in the request.
- Deduplicate provider retries by message id.
- Link accounts with expiring single-use codes. Never trust a phone
  number as identity.
- The router is thin: normalize, authenticate, call an existing service,
  format, send. Zero business logic here.
- Generic apology to the user, full detail to the logs with a correlation
  id. Never send exception text to a phone.
- Per-phone rate limits, daily caps, and an admin kill switch.
- Handle unsupported message types, session windows and send failures
  explicitly.

## mobile-pwa

Trigger: any UI, offline or caching change.

Test at 360px on throttled 3G, with a keyboard, before claiming done.

Critical flows: login to library to book to read; login to AI tutor to
ask to answer to sources; login to practice to submit to results.

- Text-first, minimal JavaScript, large touch targets, readable
  contrast, semantic headings, real labels, visible focus, alt text.
  Never colour alone to convey meaning.
- Offline reading is opt-in per resource, with a size budget, an eviction
  policy and a visible way to remove downloads.
- Offline practice queues submissions and syncs idempotently on
  reconnect.
- Show estimated data usage before any download; offer a low-data mode.
- Document and test what is never cached: other students' data,
  staff-only material, credentials.

## i18n

Trigger: any user-facing string.

Every string, templates included, goes through the translation machinery
with a French catalog entry in the same commit. An English-only string is
an incomplete change.

AI prompts, refusals and error messages are language-aware: answer in the
user's language, and never silently translate quoted source material.
Resources and questions carry a language field; search and practice
filter on it.

Test that a French user gets French UI and French AI answers.

## ai-cost

Trigger: anything that calls a provider.

- Embed a chunk once per model. Never re-embed on read.
- Cache query embeddings, and cache answers keyed by school, scope,
  normalized question, model and prompt version. Invalidate when the
  underlying resources change.
- Never send a whole book to an LLM. Respect top-k and context caps.
- Log model, tokens, latency and outcome for every call.
- Enforce per-user rate limits and per-school daily and monthly budgets.
  Budget exhaustion is a graceful message, not a stack trace.
- Timeouts and bounded retries on every provider call. An outage degrades
  a feature; it never takes the site down.
- State the expected cost impact of your change in your report.

## migration-safety

Trigger: any model change.

1. Understand dependencies and existing data first.
2. Smallest coherent schema change.
3. Generate, then READ the migration.
4. Confirm it is reversible, or state explicitly that it is not and why.
5. Test upgrade from the current state AND a fresh install.
6. Never edit an applied migration. Never touch `AUTH_USER_MODEL`.
7. Any migration that rewrites or deletes existing rows needs approval
   before you write it, plus a backup step in the instructions.

Add indexes and constraints based on real access patterns. Enforce
uniqueness at the database level, not only in a form.

## perf-budget

Trigger: anything on a hot path.

Measure, change, measure again, and put the numbers in your report.

- Search p95 under one second on the school box. No unbounded query
  anywhere.
- `select_related` / `prefetch_related` on every list view. No N+1.
- Page weight small enough to open on 3G without a visible wait.
- Long operations belong in the queue, not the request.
- No cache that can serve one user another user's content. Ever.

## debugging

Trigger: investigating a failure.

Reproduce, read the entire traceback, find the root cause, fix the root
cause, add a regression test, re-run the suite, check for side effects.

Never suppress an exception to make a symptom disappear. Never "fix"
something you could not reproduce. If you are two attempts in and still
guessing, stop and report what you know.

## review

Trigger: reviewing a diff.

Read the implementation, not the description. Run the tests. Run semgrep.
Try to break it: another student's resource, another class, teacher
endpoints as a student, guessed ids, changed object ids, invalid uploads,
oversized requests, replayed webhooks.

Report findings as CRITICAL / HIGH / MEDIUM / LOW. Style preferences are
LOW and never block. Do not rewrite working architecture because you
would have built it differently. Do not revert another agent's work
automatically: understand the intent, keep what is useful, fix only what
is defensibly broken.

Default to reporting rather than editing.

---

## Mindset

simple + explicit + tested, over clever + implicit + fragile.

Conservative with architecture, aggressive with testing.

The goal is not impressive code. The goal is a system a school in
Cameroon can actually run, on its own, on bad internet, without you.