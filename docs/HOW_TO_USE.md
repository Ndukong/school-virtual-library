# School Virtual Library — How to install and use it

Everything the school needs to install, run, and operate the library day to
day, at every level: log in, add books and questions, practice, ask the AI
tutor, use WhatsApp, go offline, back up, and fix problems.

Companion documents: `docs/status.md` (phase and work-package history),
`docs/api.md` (the JSON API), `deploy/README.md` (the production Docker box),
`AGENTS.md` (project rules for developers) and `SKILLS.md` (built-in
developer guide).

---

## 1. What this is

A school-controlled digital library for a secondary school in Cameroon:

- **Library** — upload PDFs, tag them (subject, class, language, licensing),
  read them (with per-user watermarks for owned/licensed material), and
  download them with abuse limits.
- **Search** — keyword + semantic (meaning) search, permission-filtered and
  language-filterable.
- **AI Tutor** — answers grounded ONLY in the school's approved material,
  with citations to the actual source, in English or French.
- **Question bank** — teachers build and approve questions.
- **Examinations** — teachers assemble and publish exams; students practise
  them.
- **Practice** — student quizzes with instant marking, self-marking for
  structured answers, and private progress.
- **WhatsApp** — the same AI tutor and basic services over WhatsApp for
  low-end phones.
- **PWA / offline** — installable app; read saved documents and take quizzes
  offline and sync answers when back online.
- **Reports** — aggregate (never per-student) analytics for staff.

### Roles

| Role | What they can do |
|------|------------------|
| **Student** | Read/search, AI Tutor, study tools, practice, their own progress |
| **Teacher** | Everything a student can, plus upload resources, build questions/exams, see aggregate reports |
| **School admin** | Everything a teacher can, plus manage people/roles in the admin area, reset passwords |
| **Platform superuser** | Global `/admin/`: any school, audit trail, kill switches, no limits |

---

## 2. Installing it (Windows dev, works out of the box)

Prerequisite: Python 3.10+ and a terminal.

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py create_school_admin --school "Saint John's College" --username admin1
python manage.py runserver
```

Then open http://127.0.0.1:8000 and log in.

This runs on SQLite with the **mock AI provider** — search, AI answers,
practice and everything else work fully offline with no API keys. To switch
to a real AI model later, see `docs/status.md` (WP5) and `.env.example`.

> Working tree branches: one per build package — `wp/1-correctness` through
> `wp/11-api`. `master` has them all merged; `docs/status.md` is the record.

---

## 3. First-time setup

1. `python manage.py create_school_admin --school "<Name>" --username admin1`
   creates the school and its first school administrator (it asks for a
   password). This is the same as a staff account you can manage later.
2. Log in as that admin and go to the **admin area** (`/admin/`, or the link
   on the dashboard) to:
   - create **teachers** and **students** (set their role),
   - assign **classes** and **subjects**,
   - set **student admission numbers** and link teacher profiles to subjects.
3. Teachers upload the first documents (below). New uploads are processed in
   the background — see §8.1 if you are testing without a worker.

---

## 4. Every-day use

### 4.1 Logging in (all users)

- Login screen is bilingual; use the **Français/English** link to switch.
- A signed-in user's language is remembered on their account (survives
  devices). The AI tutor answers in that language too.
- 5 failed attempts in a row lock you out with a wait that grows each time
  (`LOGIN_LOCKOUT_*`). The school admin can clear it in `/admin/` under
  "Login locks".
- Sessions expire after 30 minutes idle (shared lab machines). After an
  admin resets your password you **must** change it on first login.
- **Log out** when leaving a shared machine — this also deletes offline
  copies and saved quizzes on that device.

### 4.2 Home

`/` sends you to your role's dashboard.

### 4.3 Library (all users)

- **Browse / filter** — by keyword, type (book, notes, past paper, marking
  scheme…), and **language** (English / French).
- **Read** — resource page → *Read*. Owned/licensed material is shown with a
  watermarked viewer. You can read only what your school published.
- **Download** — limited to 10 per minute and 50 per day (platform
  superusers are exempt).
- **Offline reading** — the resource page shows data cost and a
  *Save for offline reading* button; the saved copy stays on that device.
  See §6.

### 4.4 Search (all users)

Type 2+ characters. Hybrid search (keywords + meaning) returns chunks of the
books with snippets and the matching page. Use the **Language** filter to
keep results to one language.

### 4.5 AI Tutor (all users)

- Ask naturally ("Explain electromagnetic induction with an example").
- Answers are grounded **only in approved library material** and carry
  `[n]` citations; the *Sources used* section links the actual passages.
- Scoping: ask the **whole library**, or open a book/chapter in the library
  and use its *AI Tutor about this book* link to focus there.
- If the library has no answer, the tutor says so honestly **without** using
  the AI (and without inventing content or citations).
- Limits: ~10 asks per user per minute; the school budget is configurable
  (`AI_BUDGET_*`, 0 = unlimited).
- **Study tools** (in the AI menu): summary, revision notes,
  definitions/formulae, and practice questions generated **from the source
  material only**. These are AI study *support* and are clearly labelled as
  never teacher-approved.

### 4.6 Practice (students)

- **Start a quiz**: subject + topic (optional) + length + **language**.
  Questions are drawn from approved questions only.
- Objective questions (MCQ / True-False) are graded instantly; structured
  and essay answers are self-marked against the teacher's scheme after
  submission.
- **Progress** shows your own attempts, averages, and weak topics; nobody
  else sees it.
- Teachers can publish an **exam**; students practise a finished exam the
  same way.

### 4.7 Reports (teachers and admins)

`Reports` shows school-level aggregates: library usage, AI usage and
budgets, practice performance by subject/class, popular topics, and teacher
activity. Reports never name individual students or show their answers.

---

## 5. Teacher / admin tasks

### 5.1 Upload a resource (Teachers + admins)

`Library → Upload a resource`:

- Accepted format: **PDF up to 100 MB**. Content is validated by inspecting
  the file, not just its name.
- Required: title, type, content **language** (English/French), PDF.
- Optional but useful: subject, class, author, ISBN, curriculum, licensing
  status (Owned/Licensed/Open access/…), who may read it (school / teachers
  only).
- Uploads queue in the background: extracted text → OCR if needed → chunks →
  embeddings → *Ready*. A document is searchable once its status shows
  *Ready* (see §8.1 for the worker).

### 5.2 Question bank (Teachers + admins)

`Question Bank` → *New question*:

- Types: MCQ, True/False, short/structured/grouped, essay, calculation,
  practical. Choose subject, class, topic, language, difficulty, Bloom
  level, marks; write the correct answer/answer scheme.
- Questions you create start as **Draft**; submit for review → *Pending
  review*; the approver (teacher/admin) approves or rejects. **Only
  APPROVED questions are used in practice and exams.** It is never
  auto-approved.
- The bank has an import view for bulk entry; imported questions land in the
  review queue.

### 5.3 Examinations (Teachers + admins)

`Exams` → *New exam*: pick subject/class and assemble questions with a
deterministic, balanced selection. Print clean papers (with or without the
answer key). Publishing makes the exam visible for student practice.

### 5.4 Managing people (School admins, in `/admin/`)

- **Users**: create teachers/students, change roles, deactivate accounts.
  A school admin can only manage their own school and can never grant
  staff/superuser rights.
- **Reset a password**: the *Reset password* list under your profile (or the
  admin area) issues a one-time credential; the user must change it on next
  login.
- **Lockouts**: `Login events` show failed attempts; the admin action
  *Unlock login* clears the backoff.

### 5.5 Platform superuser

Everything across all schools, plus:
- **Audit trail** (`Audit events` in `/admin/`): append-only log of
  privileged actions — user role/status changes, user deletions, and
  resource deletions, including who and when. Nobody can edit or delete the
  trail.
- Rules and limits that are school-configurable.

---

## 6. Offline / PWA (students especially)

- Install the app: open the site and use your browser's *Install/Add to Home
  screen* (the manifest is served automatically).
- **Offline reading**: on a resource page, *Save for offline reading* shows
  the data cost and stores it on the device. Offline, open it again
  normally — it loads from the device, never a stale copy of something else.
- **Offline practice**: on a quiz, *Take this quiz offline* stores it. Answer
  it without the internet; answers are queued on the device and submitted
  automatically when the connection returns (in order, to the same endpoint
  the online form uses, so the server still checks ownership).
- If you never explicitly save something, the app never stores it offline.
  When you log out, all saved offline copies are erased from that device.

---

## 7. WhatsApp channel (optional)

Two pieces:

1. **Worker** (runs the channel):
   ```powershell
   python manage.py process_whatsapp --loop
   ```
2. **Meta/WhatsApp Business config** (via `.env`):
   - `WHATSAPP_VERIFY_TOKEN` — your own token for the verification handshake.
   - `WHATSAPP_APP_SECRET` — Meta app secret; the webhook **fails closed**
     when a signature is missing or wrong.
   - `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID` — to send messages
     (leave provider as `console` to log outbound instead of sending).
   - Webhook URLs: `https://<your-host>/whatsapp/webhook/verify/` and
     `https://<your-host>/whatsapp/webhook/`.

How a user talks to the library: they send a message to the WhatsApp number;
the staff links the phone via the `whatsapp_link_code` command and reads the
returned code. From then on the number can ask the AI Tutor (scoped to the
school) and use the same honest-refusal behaviour.

Safety rails (built-in):
- Replying to a phone is only allowed inside Meta's 24-hour window and up to
  `WHATSAPP_DAILY_MESSAGE_CAP` (default 20) per number per day.
- The worker never sends internal error text; failures return a fixed
  polite "please try later" message and log the real cause under the task's
  correlation id.
- Kill switch: `python manage.py whatsapp_switch off` / `on` / `status`
  (or use the admin `WhatsApp kill switch`). Off = the webhook acknowledges
  but drops everything.

---

## 8. Operations

### 8.1 Background worker

Documents and WhatsApp are processed by **database-backed workers**, not by
the website request. For single-user testing Windows, run one terminal:

```powershell
python manage.py process_documents --loop
```

(and, if using WhatsApp, `python manage.py process_whatsapp --loop`).
In the Docker stack these are separate containers ("worker_documents" and
"worker_whatsapp").

> OCR: to text-search scanned PDFs, the machine needs Tesseract + Ghostscript
> (`DOCUMENTS_OCR_*` docs in `docs/status.md`, WP4). Without them, scanned
> pages are honestly marked "needs review" instead of faking a text layer.

### 8.2 Configuration

All knobs live in `.env` (see `.env.example` for every option). Highlights:

| Setting | Meaning | Default |
|---|---|---|
| `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS` | Django basics; `DEBUG=False` refuses the dev secret | dev-safe |
| `DATABASE_URL` | PostgreSQL URL; unset = SQLite | — |
| `AI_PROVIDER` / `AI_CHAT_PROVIDER` | `mock` (offline) / `local` (fastembed) / `openai_compatible` / `gemini` | `mock` |
| `AI_RATE_LIMIT_PER_MINUTE` | per-user AI asks/min | 10 |
| `AI_BUDGET_DAILY_REQUESTS`, … | per-school monthly/daily request & token budgets (0 = unlimited) | 0 |
| `AI_RETENTION_DAYS` | how long AI history is kept (0 = keep forever) | 0 |
| `LIBRARY_DOWNLOAD_PER_MINUTE` / `DAILY_CAP` | download abuse limits | 10 / 50 |
| `WHATSAPP_*` | channel settings incl. daily message cap | §7 |
| `SEARCH_PGVECTOR_DIM` | vector dimension on PostgreSQL (768 = e5-large) | 768 |

### 8.3 Health check

`GET /healthz/` → JSON `{"database": "ok", "queue_pending": n}` (HTTP 503 if
the database is unreachable). The Docker stack's web container healthcheck
uses it; load balancers and monitors can point at it.

### 8.4 Retention & export (data protection)

```powershell
python manage.py purge_old_ai_data --days 180 --dry-run   # preview
python manage.py purge_old_ai_data --days 180             # actually purge
python manage.py export_user_data offstu --out export.json # data-subject export
```

Retention is disabled by default (`AI_RETENTION_DAYS=0`): the purge command
**refuses** to delete anything unless you enable retention or pass `--days`
explicitly. Budget/cost records are never purged.

### 8.5 Backups & restore (production)

See `deploy/README.md`. On the school LAN box (Docker stack):

- `deploy/backup.sh` — nightly `pg_dump` + media archive to an external
  drive (`BACKUP_DIR`), running from a systemd timer at `Africa/Douala`.
- `deploy/restore.sh` — the destructive restore drill: stop the app, replace
  the database, restore media, bring the stack back and require `/healthz/`
  to pass. **Execute this drill once per term.**

### 8.6 CI

`.github/workflows/ci.yml` runs the full gate (lint, checks, full test
suite under `config.settings_test`, `check --deploy`, pip-audit, locale
freshness) on every push/PR on Ubuntu (Python 3.12) and Windows (3.10).

### 8.7 The developer gate (before any change is "done")

```powershell
.venv\Scripts\ruff.exe check .
python manage.py check
python manage.py check --settings=config.settings_test
python manage.py test --settings=config.settings_test
.venv\Scripts\pip-audit.exe
```

---

## 9. JSON API (for apps/integrations)

Session-authenticated JSON under `/api/v1/` — full contract in `docs/api.md`.
Endpoints: `resources/`, `search/`, `ask/`, `answers/<public_id>/`,
`questions/`. Same security as the web (school-scoped, owner-or-404,
rate-limited `ask`).

---

## 10. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `ImproperlyConfigured` on boot | `DEBUG=False` with the dev `SECRET_KEY` or empty `ALLOWED_HOSTS`. Set them properly (deploy stack does). |
| Login rejected though password is right | You hit the failed-attempt lockout; wait, or an admin unlocks `Login locks`. New password resets force a change. |
| Uploaded PDF never becomes searchable | No `process_documents --loop` worker running, or OCR marked pages `needs review` for scanned material. Check the resource page status. |
| AI Tutor refuses "no relevant material" | Grounded scope has nothing matching yet, or the document isn't *Ready*. AI won't guess. |
| `429` on AI asks | Per-minute limit hit; wait ~a minute or raise `AI_RATE_LIMIT_PER_MINUTE`. |
| French/English not showing | Use the language link; a signed-in user's language is their account setting. |
| WhatsApp replies not sending | Check the worker, `whatsapp_switch status`, the 24-hour window, and `WHATSAPP_DAILY_MESSAGE_CAP`. |
| Offline copy not opening offline | It must be saved while online from the resource page, then opened from the *same device/browser profile*. |
| `/healthz/` returns 503 | The database is unreachable; check PostgreSQL/volume. |
| `check --deploy` warnings | Read them — the deploy gate is intentionally strict; don't silence. |

---

## 11. Where everything lives

| Thing | Location |
|---|---|
| Code | Django apps `accounts library documents search ai question_bank examinations learning whatsapp pwa reports api common` |
| Templates | `templates/` (bilingual, French catalog in `locale/`) |
| Source of truth | `docs/status.md` |
| JSON API | `docs/api.md` |
| Production box | `deploy/README.md`, `deploy/docker-compose.prod.yml` |
| Env options | `.env.example` |