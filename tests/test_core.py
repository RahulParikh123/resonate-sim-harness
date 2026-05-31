"""Tests for the wiring logic that doesn't need API keys: budget cap, JSON
parsing, judge author-exclusion, and config loading.

    python3 tests/test_core.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness.config import DEFAULT_REVIEWERS, load_config  # noqa: E402
from harness.llm import Budget, BudgetExceeded, safe_json  # noqa: E402
from harness.reviewers import _VERDICT_SEVERITY  # noqa: E402
from harness.schemas import Severity  # noqa: E402


class BudgetTests(unittest.TestCase):
    def test_under_cap_ok(self):
        Budget(cap_usd=1.0).check()  # no raise

    def test_over_cap_raises(self):
        b = Budget(cap_usd=0.01)
        b.add(0.02)
        with self.assertRaises(BudgetExceeded):
            b.check()

    def test_add_accumulates_and_counts(self):
        b = Budget(cap_usd=10.0)
        b.add(0.5)
        b.add(0.25)
        self.assertAlmostEqual(b.spent_usd, 0.75)
        self.assertEqual(b.calls, 2)


class SafeJsonTests(unittest.TestCase):
    def test_fenced(self):
        self.assertEqual(safe_json('```json\n{"a": 1}\n```'), {"a": 1})

    def test_surrounded_by_prose(self):
        self.assertEqual(safe_json('Here you go: {"b": 2}. Done.'), {"b": 2})

    def test_garbage_returns_none(self):
        self.assertIsNone(safe_json("not json at all"))


class ReviewerTests(unittest.TestCase):
    def test_verdict_to_severity(self):
        self.assertEqual(_VERDICT_SEVERITY["fail"], Severity.HIGH)
        self.assertEqual(_VERDICT_SEVERITY["concern"], Severity.MEDIUM)
        self.assertIsNone(_VERDICT_SEVERITY["meets"])

    def test_default_reviewers_are_well_formed(self):
        self.assertTrue(DEFAULT_REVIEWERS)
        self.assertTrue(all(r.name and r.model and r.criteria for r in DEFAULT_REVIEWERS))


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.cfg = load_config(ROOT / "configs" / "example.harness.toml")

    def test_basics(self):
        self.assertEqual(self.cfg.name, "default-smoke")
        self.assertEqual(self.cfg.rubric.sms_max_chars, 320)

    def test_reviewers_loaded(self):
        self.assertGreaterEqual(len(self.cfg.reviewers), 3)
        self.assertTrue(all(r.criteria for r in self.cfg.reviewers))

    def test_dimensions_enabled(self):
        self.assertIn("scaffolding_leak", self.cfg.enabled_dimensions)
        self.assertGreaterEqual(len(self.cfg.enabled_dimensions), 6)

    def test_cell_count_positive(self):
        self.assertGreater(self.cfg.cell_count, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
