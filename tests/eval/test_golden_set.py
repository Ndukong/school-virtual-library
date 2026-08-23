"""RAG regression harness (stub).

Work Package 11 implements the scoring. Until the fixture corpus exists
this module SKIPS rather than fails, so it never blocks the gate.

When implemented, this must report:
  - citation precision / recall against expected_pages
  - refusal accuracy on expect == "refusal" cases (and assert the provider
    was never called)
  - injection resistance on injection-* cases
  - answer-length and latency drift

A regression in refusal accuracy or injection resistance blocks the change.
"""

import json
import unittest
from pathlib import Path

from django.test import TestCase

EVAL_DIR = Path(__file__).resolve().parent
GOLDEN_SET = EVAL_DIR / "golden_set.json"
CORPUS_DIR = EVAL_DIR / "corpus"


def load_cases():
    with GOLDEN_SET.open(encoding="utf-8") as handle:
        return json.load(handle)["cases"]


class GoldenSetIntegrityTests(TestCase):
    """Always runs. Guards the file itself against rot."""

    def test_golden_set_is_valid_and_well_formed(self):
        cases = load_cases()
        self.assertGreater(len(cases), 0)

        seen = set()
        for case in cases:
            for field in ("id", "question", "scope", "expect", "corpus_ref"):
                self.assertIn(field, case, f"{case.get('id')} missing {field}")
            self.assertIn(case["expect"], {"grounded", "refusal"})
            self.assertNotIn(case["id"], seen, f"duplicate case id {case['id']}")
            seen.add(case["id"])
            if case["expect"] == "refusal":
                self.assertEqual(case.get("expected_pages", []), [])

    def test_has_a_refusal_and_an_injection_case(self):
        ids = [case["id"] for case in load_cases()]
        self.assertTrue(any(i.startswith("refusal-") for i in ids))
        self.assertTrue(any(i.startswith("injection-") for i in ids))


@unittest.skipUnless(
    CORPUS_DIR.exists(),
    "eval corpus not built yet - implemented in Work Package 11",
)
class RagEvalTests(TestCase):
    def test_citation_precision_and_recall(self):
        self.fail("not implemented: Work Package 11")

    def test_refuses_out_of_corpus_questions_without_calling_provider(self):
        self.fail("not implemented: Work Package 11")

    def test_ignores_instructions_embedded_in_retrieved_documents(self):
        self.fail("not implemented: Work Package 11")