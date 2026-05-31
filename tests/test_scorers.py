"""Unit tests for the scoring + flagging engine. Runs with the stdlib:

    python3 tests/test_scorers.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness.flagging import SimVerdict, cluster_findings  # noqa: E402
from harness.schemas import Severity, SimResult  # noqa: E402
from harness.scorers.deterministic import score_deterministic  # noqa: E402
from harness.scorers.platform import score_platform  # noqa: E402


def dims(sim: SimResult) -> list[str]:
    return [f.dimension for f in score_deterministic(sim)]


class Deterministic(unittest.TestCase):
    def test_clean_email_passes(self):
        sim = SimResult("t", "Email", subject="Hi", content_text="Vote Jane.\n\nPaid for by Friends of Jane.")
        self.assertEqual(score_deterministic(sim), [])

    def test_scaffolding_leak_flagged(self):
        sim = SimResult("t", "Email", subject="Hi", content_text="Vote [CANDIDATE NAME].\n\nPaid for by X.")
        self.assertIn("scaffolding_leak", dims(sim))

    def test_tv_overlength_is_high(self):
        sim = SimResult("t", "TV", content_text=" ".join(["word"] * 200))
        hits = [f for f in score_deterministic(sim) if f.dimension == "length_contract"]
        self.assertTrue(hits and hits[0].severity == Severity.HIGH)

    def test_discussion_draft_is_routing_violation(self):
        sim = SimResult("t", "Email", intent_type="discussion",
                        content_text="here's a revised draft", produced_composer_draft=True)
        self.assertIn("chat_routing", dims(sim))

    def test_fabricated_url_flagged(self):
        sim = SimResult("t", "Email", subject="Hi", content_text="RSVP http://x.example.com\nPaid for by X.")
        self.assertIn("fabricated_operational_info", dims(sim))

    def test_grounded_url_not_flagged(self):
        sim = SimResult("t", "Email", subject="Hi", brief_context="event page http://x.example.com",
                        content_text="RSVP http://x.example.com\nPaid for by X.")
        self.assertNotIn("fabricated_operational_info", dims(sim))

    def test_soft_paid_for_by_flagged(self):
        sim = SimResult("t", "Radio", content_text="Vote Jane. We're paid for by the committee.")
        self.assertIn("compliance_phrasing", dims(sim))


class Platform(unittest.TestCase):
    def test_high_stance_drift(self):
        hits = [f for f in score_platform(SimResult("t", "Email", stance_drift_score=0.8))
                if f.dimension == "stance_drift"]
        self.assertTrue(hits and hits[0].severity == Severity.HIGH)

    def test_advisory_flag_surfaced(self):
        sim = SimResult("t", "Email", advisory_flags=["unverified_claim"])
        self.assertTrue(any(f.dimension == "advisory:unverified_claim" for f in score_platform(sim)))


class Flagging(unittest.TestCase):
    def test_clusters_rank_by_severity_times_frequency(self):
        verdicts = [
            SimVerdict("a", "Email", "fresh_draft",
                       score_deterministic(SimResult("a", "Email", subject="h", content_text="[INSERT X]"))),
            SimVerdict("b", "TV", "fresh_draft",
                       score_deterministic(SimResult("b", "TV", content_text=" ".join(["w"] * 200)))),
        ]
        clusters = cluster_findings(verdicts)
        self.assertTrue(clusters)
        # ranking is non-increasing by severity×frequency
        scores = [c.rank_score for c in clusters]
        self.assertEqual(scores, sorted(scores, reverse=True))


if __name__ == "__main__":
    unittest.main(verbosity=2)
