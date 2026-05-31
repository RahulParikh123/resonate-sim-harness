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

from harness.config import DEFAULT_JOBS, DEFAULT_REVIEWERS, load_config, rotate_reviewers  # noqa: E402
from harness.llm import Budget, BudgetExceeded, safe_json  # noqa: E402
from harness.reviewers import _VERDICT_SEVERITY, aggregate_quality  # noqa: E402
from harness.schemas import Severity  # noqa: E402


class BudgetTests(unittest.TestCase):
    def test_under_cap_ok(self):
        Budget(per_model_cap=1.0).check("m")  # no raise

    def test_over_cap_raises(self):
        b = Budget(per_model_cap=0.01)
        b.add("m", 0.02)
        with self.assertRaises(BudgetExceeded):
            b.check("m")

    def test_per_model_isolation(self):
        b = Budget(per_model_cap=1.0)
        b.add("a", 2.0)
        with self.assertRaises(BudgetExceeded):
            b.check("a")
        b.check("b")  # a different model, still under its own cap → no raise

    def test_add_accumulates_and_counts(self):
        b = Budget(per_model_cap=10.0)
        b.add("m", 0.5)
        b.add("m", 0.25)
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

    def test_jobs_are_three_axes_with_a_guardrail(self):
        self.assertEqual(len(DEFAULT_JOBS), 3)
        roles = {j.key: j.role for j in DEFAULT_JOBS}
        self.assertEqual(roles.get("guardrail"), "guardrail")
        self.assertEqual(sum(1 for j in DEFAULT_JOBS if j.role == "reward"), 2)

    def test_aggregate_is_reward_mean_when_guardrail_clean(self):
        reviews = [
            {"role": "reward", "score": 80, "verdict": "meets"},
            {"role": "reward", "score": 60, "verdict": "meets"},
            {"role": "guardrail", "score": 100, "verdict": "meets"},
        ]
        self.assertEqual(aggregate_quality(reviews), 70.0)  # mean(80,60); guardrail clean → no cap

    def test_guardrail_fail_caps_the_score(self):
        reviews = [
            {"role": "reward", "score": 95, "verdict": "meets"},
            {"role": "reward", "score": 90, "verdict": "meets"},
            {"role": "guardrail", "score": 10, "verdict": "fail"},
        ]
        self.assertLessEqual(aggregate_quality(reviews), 35.0)  # a liability can't be bought back with good copy


class RotationTests(unittest.TestCase):
    MODELS = ["claude", "gpt", "gemini", "grok", "kimi"]

    def test_offset_assigns_each_job_a_model(self):
        revs = rotate_reviewers(DEFAULT_JOBS, self.MODELS, offset=0)
        self.assertEqual(len(revs), len(DEFAULT_JOBS))
        self.assertEqual([r.name for r in revs], [j.name for j in DEFAULT_JOBS])
        # offset 0 → the first len(jobs) models, in order
        self.assertEqual([r.model for r in revs], self.MODELS[:len(DEFAULT_JOBS)])

    def test_offset_rotates_models(self):
        n = len(self.MODELS)
        r1 = [r.model for r in rotate_reviewers(DEFAULT_JOBS, self.MODELS, 1)]
        self.assertEqual(r1, [self.MODELS[(i + 1) % n] for i in range(len(DEFAULT_JOBS))])

    def test_latin_square_full_coverage(self):
        # Across offsets 0..N-1, every job is played by every model exactly once.
        seen = {j.name: set() for j in DEFAULT_JOBS}
        for offset in range(len(self.MODELS)):
            for r in rotate_reviewers(DEFAULT_JOBS, self.MODELS, offset):
                seen[r.name].add(r.model)
        for job, models in seen.items():
            self.assertEqual(models, set(self.MODELS), f"{job} did not see every model")


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
