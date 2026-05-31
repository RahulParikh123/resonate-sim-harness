"""SimRunner — orchestrates scoring → flagging → store.

Dry-run mode scores fixtures with the deterministic + platform layers only
(no network, no keys). Live mode (wired once backend + keys are in) fans out
council briefs through ResonateClient, then adds the judge panel for sims that
survive the cheap layers.

The rubric (from the config) drives thresholds, which dimensions are active,
and per-dimension severity overrides.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from .config import HarnessConfig, RubricConfig
from .flagging import Cluster, SimVerdict, cluster_findings
from .reviewers import reviews_to_findings
from .schemas import Finding, Severity, SimResult
from .scorers.deterministic import score_deterministic
from .scorers.platform import score_platform
from .store import Store


def apply_rubric(findings: list[Finding], rubric: RubricConfig) -> list[Finding]:
    """Drop disabled dimensions; apply per-dimension severity overrides."""
    out: list[Finding] = []
    for f in findings:
        if not rubric.is_enabled(f.dimension):
            continue
        override = rubric.override_severity(f.dimension)
        out.append(replace(f, severity=Severity(override)) if override else f)
    return out


def score_sim(sim: SimResult, rubric: RubricConfig | None = None) -> SimVerdict:
    """Cheap layers first. The judge panel (judge.py) runs in live mode only,
    and only on sims that survive these layers — it costs money."""
    rubric = rubric or RubricConfig()
    findings = score_deterministic(sim, rubric) + score_platform(sim, rubric)
    if sim.reviews:  # fixtures (or a prior live pass) may already carry reviewer concerns
        findings += reviews_to_findings(sim.reviews)
    return SimVerdict(sim.id, sim.channel, sim.intent_type, apply_rubric(findings, rubric),
                      model=sim.model, persona=sim.persona, surface=sim.surface,
                      target_segment=sim.target_segment, content_text=sim.content_text,
                      quality_score=sim.quality_score, reviews=sim.reviews, preflight_qa=sim.preflight_qa)


def _load_fixtures(path: str | Path) -> list[SimResult]:
    return [SimResult.from_dict(d) for d in json.loads(Path(path).read_text())]


def run_dryrun(fixtures_path: str | Path, db_path: str = "runs/harness.db"):
    """Default-rubric dry run (used by scripts/run_dryrun.py)."""
    verdicts = [score_sim(s) for s in _load_fixtures(fixtures_path)]
    clusters = cluster_findings(verdicts)
    run_id = Store(db_path).save_run("dryrun", str(fixtures_path), verdicts, clusters)
    return run_id, verdicts, clusters


def run_with_config(config: HarnessConfig, fixtures_path: str | Path):
    """Config-driven dry run: scores fixtures using the config's rubric, stores a
    run snapshot. (Live mode swaps fixtures for council→backend draft capture.)"""
    verdicts = [score_sim(s, config.rubric) for s in _load_fixtures(fixtures_path)]
    clusters = cluster_findings(verdicts)
    snapshot = {"config_name": config.name, "target": config.target.base_url,
                "council": config.council.models, "enabled_dimensions": config.enabled_dimensions,
                "council_spent_usd": 0.0, "backend_spent_usd": 0.0, "total_usd": 0.0,
                "council_cap_usd": config.budgets.council_usd, "backend_cap_usd": config.budgets.backend_draft_usd}
    run_id = Store(config.output.db_path).save_run("dryrun", config.target.base_url, verdicts, clusters, snapshot)
    return run_id, verdicts, clusters
