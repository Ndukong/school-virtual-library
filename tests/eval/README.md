# RAG evaluation harness

Run: `python manage.py test tests.eval --settings=config.settings_test`

- `golden_set.json` - the cases. Integrity is tested on every run.
- `corpus/` - fixture documents each `corpus_ref` points at. Not built yet.
- Always runs against the mock provider. Never a paid provider.

Adding a case: give it an id prefixed `grounded-`, `refusal-`, `injection-`
or `fr-`, cite the real page numbers from the fixture, and say in `notes`
what failure mode it protects against. A case nobody can explain is a case
nobody will maintain.