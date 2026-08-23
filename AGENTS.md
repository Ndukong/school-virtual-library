# AGENTS.md
# School Virtual Library — AI Development Instructions

## 1. Purpose

This file is the persistent operating contract for AI coding agents working on the School Virtual Library project.

The project is a school-controlled digital learning platform for secondary-school students and teachers. It combines:

- Digital textbooks and educational resources
- Semantic/keyword search
- Retrieval-Augmented Generation (RAG)
- AI tutoring and study-note generation
- Question bank management
- Examination and marking-scheme generation
- Student practice
- WhatsApp access
- Responsive web/PWA access
- Teacher and administrator tools

The long-term objective is to make approved school learning resources searchable and usable through a reliable AI-assisted learning environment.

---

## 2. Agent Roles

### Lead Developer — DeepSeek V4 Flash

The lead agent owns:

- Overall architecture
- Django/backend implementation
- Database design
- APIs
- Authentication and authorization
- Library/document subsystem
- Document processing
- RAG/search
- AI provider abstraction
- Question bank
- Examination generation
- WhatsApp backend integration
- Complex debugging
- Production-readiness

Only the lead developer should normally make architectural changes.

### Reviewer / QA / UI Specialist — Big Pickle

The reviewer is an independent second pair of eyes.

Responsibilities:

- Code review
- Security review
- Test review
- UI/UX review
- Mobile/PWA review
- Accessibility review
- Performance observations
- Documentation review
- Adversarial testing
- Regression testing

The reviewer should NOT rewrite working architecture merely because it would personally implement it differently.

By default, the reviewer reports problems rather than modifying the project.

---

## 3. Agent Coordination

Do not allow two agents to modify the same codebase simultaneously.

Preferred workflow:

```text
Lead implements
      ↓
Tests
      ↓
Git commit
      ↓
Reviewer audits
      ↓
Review report
      ↓
Lead fixes
      ↓
Tests
      ↓
Git commit
```

Each completed phase must have a Git checkpoint.

Suggested commit naming:

```text
phase-00-architecture
phase-01-core-platform
phase-02-digital-library
phase-03-document-processing
phase-04-semantic-search
phase-05-ai-librarian
phase-06-ai-study-tools
phase-07-question-bank
phase-08-examination-generator
phase-09-student-practice
phase-10-whatsapp
phase-11-pwa
phase-12-analytics
```

Never rewrite history unless explicitly instructed.

---

## 4. Golden Rules

1. Inspect existing code before changing it.
2. Do not assume a file is safe to replace.
3. Preserve working functionality.
4. Do not introduce unnecessary dependencies.
5. Never hard-code secrets.
6. Never bypass authentication to make a feature work.
7. Never weaken permissions as a shortcut.
8. Use proper Django migrations for schema changes.
9. Add tests for meaningful new functionality.
10. Do not claim a feature is complete until it has been tested.
11. Prefer maintainable code over clever code.
12. Keep business logic out of templates.
13. Put complex domain operations into services/modules.
14. Use background jobs for expensive operations.
15. Keep AI-provider-specific code behind an abstraction layer.
16. Treat uploaded documents as untrusted input.
17. Never fabricate AI citations, page numbers, quotations, or sources.
18. Never expose private student data to unauthorized users.
19. Respect copyright and licensing restrictions.
20. Do not add future features prematurely.
21. Do not make architectural changes silently.
22. Keep documentation synchronized with implementation.

---

## 5. Current Phase Protocol

Before beginning work:

1. Read this file.
2. Read `README.md`.
3. Read `SKILLS.md`.
4. Inspect the repository.
5. Determine the current phase from the repository and Git history.
6. Inspect recent commits.
7. Check existing tests.
8. Identify known issues.
9. Only then make a plan.

Do not restart the project from scratch merely because the existing implementation is imperfect.

---

## 6. Phase Completion Protocol

At the end of every phase:

```text
PHASE:
STATUS: COMPLETE / INCOMPLETE

Implemented:
- ...

Tests executed:
- ...

Test results:
- ...

Known issues:
- ...

Security considerations:
- ...

Database/migrations:
- ...

Documentation updated:
- ...

Git commit:
- ...

Recommended next step:
- ...
```

A phase is not COMPLETE if critical tests fail.

---

## 7. Architecture

Preferred stack:

- Python
- Django
- Django REST Framework where APIs are needed
- PostgreSQL
- pgvector for vector search
- Redis
- Celery or an equivalent background-job system
- Object storage for large documents
- Responsive HTML/CSS/JavaScript
- PWA support
- Configurable AI provider
- WhatsApp Business Platform/API

Keep the architecture modular.

Suggested Django apps:

```text
config/
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

Do not create an app unless it has a meaningful boundary.

---

## 8. Core Domain Model

The system should conceptually contain:

```text
School
 ├── Users
 ├── Classes
 ├── Subjects
 ├── Students
 ├── Teachers
 └── Resources

Resource
 ├── Book
 ├── Notes
 ├── Past Paper
 ├── Marking Scheme
 └── Other educational documents

Book
 ├── Chapters
 │    └── Sections
 │         └── Document chunks
 └── Metadata

DocumentChunk
 ├── text
 ├── page number
 ├── metadata
 └── embedding

Question
 ├── topic
 ├── subtopic
 ├── Bloom level
 ├── difficulty
 ├── marks
 ├── answer
 └── marking scheme

Examination
 ├── configuration
 ├── questions
 ├── answer key
 └── marking scheme

LearningActivity
 ├── book access
 ├── AI usage
 ├── practice
 └── progress
```

Use foreign keys, constraints and indexes appropriately.

Use UUIDs for externally exposed identifiers where useful.

---

## 9. Authentication and Authorization

Roles:

### Administrator
Full school-level management.

### Teacher
Authorized teaching, library, question-bank and examination functions.

### Student
Only permitted learning resources and student functionality.

Use Django groups/permissions or a well-designed role system.

Do not scatter role checks throughout templates and views.

Prefer centralized permission classes/policies.

Test both allowed and denied access.

---

## 10. Library Rules

Resources must contain useful metadata, including where applicable:

- title
- author
- publisher
- edition
- ISBN
- subject
- class/form
- curriculum
- language
- description
- publication year
- uploader
- access policy
- licensing status
- processing status

Possible licensing statuses:

```text
OWNED
LICENSED
OPEN_ACCESS
PUBLIC_DOMAIN
TEACHER_CREATED
SCHOOL_CREATED
UNKNOWN
```

The application must not encourage unauthorized distribution of copyrighted material.

---

## 11. Document Processing

Pipeline:

```text
Upload
 ↓
Validate
 ↓
Store original
 ↓
Extract text
 ↓
OCR if necessary
 ↓
Detect structure
 ↓
Chunk
 ↓
Generate embeddings
 ↓
Index
 ↓
READY
```

Processing states should include:

```text
UPLOADED
VALIDATING
EXTRACTING
OCR_PROCESSING
CHUNKING
EMBEDDING
READY
FAILED
```

Document processing must be asynchronous for expensive jobs.

The original document must never be modified during processing.

Store extraction results separately.

---

## 12. RAG Rules

Use Retrieval-Augmented Generation for library-grounded answers.

Pipeline:

```text
Question
 ↓
Identify scope
 ↓
Retrieve relevant chunks
 ↓
Filter by permissions/metadata
 ↓
Rank
 ↓
Construct context
 ↓
Generate response
 ↓
Attach citations
```

Supported scopes:

- General AI
- Whole school library
- Subject
- Class/form
- Book
- Chapter
- Section

When a user asks about a selected book, retrieval must prioritize that book and not silently search unrelated material.

The AI must say when the selected material is insufficient.

Never fabricate:

- sources
- pages
- quotations
- textbook claims

---

## 13. AI Provider Abstraction

Never scatter provider SDK calls across the project.

Create a provider interface/service.

Conceptually:

```python
class AIProvider:
    def generate(...)
    def embed(...)
```

Possible implementations:

```text
DeepSeekProvider
OpenAICompatibleProvider
LocalProvider
MockAIProvider
```

Provider/model configuration belongs in environment/configuration.

The rest of the application should not care which provider is being used.

---

## 14. AI Cost and Reliability

Implement:

- caching where safe
- token/request tracking
- configurable models
- retries
- timeouts
- rate limits
- failure handling
- reusable embeddings
- background processing

Do not call an embedding API every time the same document is searched.

Do not send the entire textbook to an LLM for every question.

---

## 15. Question Bank

Questions should support:

- subject
- class/form
- topic
- subtopic
- type
- difficulty
- marks
- Bloom level
- source
- chapter
- page where available
- answer
- marking scheme
- author
- approval status

Question types:

- MCQ
- True/False
- Short Structural Question
- Structured Question
- Grouped Structural Question
- Essay
- Calculation
- Practical
- Other configurable types

Prefer approved questions before generating new ones.

---

## 16. Examination Generation

Teachers must specify:

- subject
- class
- topics
- marks
- duration
- question types
- difficulty
- Bloom distribution
- source scope

The system should:

1. Select approved questions where possible.
2. Generate new questions only when needed.
3. Avoid duplicates.
4. Validate marks.
5. Validate topic coverage.
6. Validate Bloom distribution.
7. Validate difficulty.
8. Generate answers.
9. Generate marking scheme.
10. Require teacher review.

Never automatically publish an AI-generated examination.

---

## 17. Bloom Taxonomy

Support:

- Knowledge
- Comprehension
- Application
- Analysis
- Synthesis
- Evaluation

Allow configurable distributions.

The system should report actual versus requested distribution.

---

## 18. Student Learning

Students should be able to:

- browse resources
- search
- read
- bookmark
- ask AI
- generate revision notes where permitted
- practice questions
- receive explanations
- view their own progress

Do not expose private analytics to other students.

---

## 19. WhatsApp

WhatsApp is an interface, not the database.

Architecture:

```text
WhatsApp
 ↓
Webhook
 ↓
Django
 ↓
Authentication
 ↓
Library / AI / Question Bank
 ↓
Response
```

Do not duplicate business logic in the WhatsApp module.

Use account linking rather than trusting phone numbers blindly.

Verify webhooks.

Rate-limit requests.

Do not expose student records through unauthorized WhatsApp sessions.

---

## 20. PWA / Mobile

The student UI is mobile-first.

Prioritize:

- low bandwidth
- fast loading
- large touch targets
- readable typography
- minimal JavaScript
- responsive document reading
- efficient image loading
- caching where safe

Primary navigation:

```text
Home
Library
Search
Practice
AI Tutor
Profile
```

---

## 21. Security

Always consider:

- authentication
- authorization
- CSRF
- XSS
- SQL injection
- file upload attacks
- malicious PDFs
- path traversal
- insecure direct object references
- API abuse
- rate limiting
- webhook spoofing
- secret leakage
- private storage access
- excessive data exposure

Never trust uploaded files or client-supplied IDs.

Never use user-provided filenames directly as filesystem paths.

---

## 22. Student Privacy

Minimize student data.

Do not log:

- passwords
- API keys
- unnecessary personal information

Do not expose student performance publicly.

Use authorization checks on every sensitive endpoint.

---

## 23. Testing

Minimum testing categories:

### Unit
Models, services, utilities.

### API
Authentication, permissions, CRUD, search, AI endpoints.

### Integration
Upload → extraction → chunking → embedding → search → RAG.

### Security
Unauthorized access and privilege escalation.

### Regression
Existing functionality after every significant change.

### UI
Critical mobile and desktop flows.

---

## 24. Windows Development

The project must remain easy to run on Windows.

Provide:

```text
README.md
.env.example
requirements.txt or pyproject.toml
manage.py
```

If Docker is used, provide appropriate Docker files.

Document:

- prerequisites
- environment setup
- database setup
- migrations
- test commands
- development server
- Celery/worker setup
- Redis setup
- AI configuration

---

## 25. Git Discipline

Before meaningful work:

```bash
git status
git log --oneline -10
```

After meaningful work:

```bash
git diff
python manage.py check
python manage.py test
git status
```

Commit coherent changes.

Avoid giant unrelated commits.

Never commit:

- `.env`
- API keys
- passwords
- private student data
- huge generated files unless intentionally versioned

---

## 26. Reviewer Protocol

When acting as reviewer:

1. Inspect the actual implementation.
2. Run tests where possible.
3. Look for security flaws.
4. Look for broken permissions.
5. Look for database inefficiencies.
6. Look for race conditions/background-job problems.
7. Test mobile usability.
8. Check documentation.
9. Prioritize findings.

Use severity:

```text
CRITICAL
HIGH
MEDIUM
LOW
```

Do not report stylistic preferences as critical problems.

---

## 27. When Requirements Are Ambiguous

Do not invent major requirements.

If ambiguity affects architecture, ask for clarification.

If ambiguity is minor, make a reasonable choice and document it.

Do not repeatedly ask questions whose answers can safely be inferred from the existing project documentation.

---

## 28. Definition of Done

A feature is DONE only when:

- implementation exists
- migrations exist if needed
- tests exist where appropriate
- tests pass
- permissions are tested
- errors are handled
- documentation is updated
- UI works at intended viewport sizes
- no secrets are committed
- no known critical issue remains

---

## 29. Long-Term Vision

The system should eventually become a unified digital school learning platform:

```text
                 SCHOOL DIGITAL CAMPUS
                         |
       +-----------------+-----------------+
       |                 |                 |
    LIBRARY           AI TUTOR        QUESTION BANK
       |                 |                 |
   Textbooks         Explain          Practice
   Notes             Summarize        Exams
   Past Papers       Tutor            Marking
       |                 |                 |
       +-----------------+-----------------+
                         |
                    STUDENT
                   /       \
                Web/PWA   WhatsApp
                         |
                 Personalized
                    Learning
```

Build toward this vision without over-engineering the first release.
