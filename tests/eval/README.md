# RAG evaluation harness

Run: `python manage.py test tests.eval --settings=config.settings_test`

- `golden_set.json` - the cases. Integrity is tested on every run.
- `harness.py` - the fixture-corpus specs AND the reference chat provider.
  The corpus is built at test time as DocumentChunk rows (no binaries); each
  page is its own chunk so `expected_pages` are directly measurable.
- Runs against the MOCK provider + the reference provider. Never a paid
  provider, never a network call.
- Scoring: grounding phrase presence, citation precision/recall vs
  expected_pages, refusal accuracy (with zero provider calls), injection
  resistance (instruction text inside the corpus is blocked and the system
  prompt still carries the DATA/instructions defence).

Adding a case: give it an id prefixed `grounded-`, `refusal-`, `injection-`
or `fr-`, add the page text to `tests/eval/harness.py:CORPUS`, cite the real
pages in `expected_pages`, and say in `notes` what failure mode it protects
against. A case nobody can explain is a case nobody will maintain.