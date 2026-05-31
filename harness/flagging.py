"""Combine findings into a per-sim verdict, then cluster flags for triage.

Goal: the reviewer lands on ~30 *patterns*, not 10,000 rows. MVP clustering
groups by failed dimension (+ channel breakdown); Phase 3 swaps in embedding +
HDBSCAN clustering for finer-grained "same failure" grouping.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .schemas import Finding, Severity, severity_rank


@dataclass
class SimVerdict:
    sim_id: str
    channel: str
    intent_type: str
    findings: list[Finding]
    model: str = ""
    persona: str = ""
    surface: str = ""
    quality_score: float | None = None
    reviews: list = field(default_factory=list)
    preflight_qa: list = field(default_factory=list)

    @property
    def severity(self) -> Severity | None:
        if not self.findings:
            return None
        return max((f.severity for f in self.findings), key=severity_rank)

    @property
    def passed(self) -> bool:
        return not self.findings


@dataclass
class Cluster:
    dimension: str
    severity: Severity
    size: int = 0
    channels: dict[str, int] = field(default_factory=dict)
    example_sim_id: str | None = None
    example_evidence: str | None = None

    @property
    def rank_score(self) -> int:
        return _SEV_WEIGHT[self.severity] * self.size


_SEV_WEIGHT = {Severity.CRITICAL: 8, Severity.HIGH: 4, Severity.MEDIUM: 2, Severity.LOW: 1}


def cluster_findings(verdicts: list[SimVerdict]) -> list[Cluster]:
    """Group flags by dimension; rank by severity × frequency (biggest harms first)."""
    buckets: dict[str, Cluster] = {}
    for v in verdicts:
        for f in v.findings:
            c = buckets.get(f.dimension)
            if c is None:
                c = Cluster(dimension=f.dimension, severity=f.severity,
                            example_sim_id=v.sim_id, example_evidence=f.evidence)
                buckets[f.dimension] = c
            c.size += 1
            c.channels[v.channel] = c.channels.get(v.channel, 0) + 1
            if severity_rank(f.severity) > severity_rank(c.severity):
                c.severity, c.example_sim_id, c.example_evidence = f.severity, v.sim_id, f.evidence

    clusters = list(buckets.values())
    clusters.sort(key=lambda c: -c.rank_score)
    return clusters


def summarize_by(verdicts: list[SimVerdict], key) -> dict[str, dict]:
    """Group verdicts by a key fn (e.g. by model, by persona) → per-group
    {total, flagged, pass_rate, severities}. This is what powers the
    'differentiate by model and persona' breakdown in the output."""
    groups: dict[str, dict] = {}
    for v in verdicts:
        k = key(v) or "—"
        g = groups.setdefault(k, {"total": 0, "flagged": 0, "severities": {}})
        g["total"] += 1
        if not v.passed:
            g["flagged"] += 1
            s = v.severity.value
            g["severities"][s] = g["severities"].get(s, 0) + 1
    for g in groups.values():
        g["pass_rate"] = round(100 * (g["total"] - g["flagged"]) / g["total"]) if g["total"] else 0
    return groups
