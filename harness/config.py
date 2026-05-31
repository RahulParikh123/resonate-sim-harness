"""Config model + loader. The TOML config IS the set of human gates.

Loaded with stdlib `tomllib` (Python 3.11+), so a config-driven run needs no
install. Each named config file = one reproducible, shareable simulation your
cofounders can edit and re-run.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TargetConfig:
    base_url: str = "http://localhost:8000"
    dev_email: str = "harness-operator@example.com"
    bearer_token: str = ""


@dataclass
class CouncilConfig:
    # The five-model council. These models BOTH generate varied campaign requests AND
    # rotate across the review jobs. One model per provider = the diversity backbone.
    models: list[str] = field(default_factory=lambda: ["claude", "gpt", "gemini", "grok", "kimi"])
    personas: list[str] = field(default_factory=list)


@dataclass
class Reviewer:
    """One review axis bound to the model performing it this simulation. The model
    judges Grok's draft against `criteria`; it never rewrites. `role` decides whether
    the score feeds the headline (reward) or acts as a gate (guardrail)."""
    name: str
    model: str
    criteria: str
    role: str = "reward"


# Default review council — each reviewer PROXIES a point of view. Most are voters
# the message is trying to reach; two are craft/guardrail roles. Edit freely in the
# Configure page. They review Grok's draft — they never rewrite it.
DEFAULT_REVIEWERS: list[Reviewer] = [
    Reviewer("Target-segment voter", "judge/sonnet",
             "You ARE the specific voter group this message is tailored to. Judge it the way that group would: "
             "does it actually speak to our lives, language, and values, or is it a stereotype / generic pander? "
             "If tailoring is claimed (e.g. to a community), verify it genuinely lands for us. High bar for authenticity."),
    Reviewer("Skeptical swing voter", "judge/gpt",
             "You are an undecided, time-poor swing voter who distrusts politicians. Judge whether this actually "
             "moves you or reads as spin, cliché, or hot air. You have a low tolerance for cringe and over-claiming; "
             "you reward concrete, believable, human messages with one clear point."),
    Reviewer("Energized base voter", "judge/gemini",
             "You are a committed supporter who wants to be fired up and share this. Judge whether it has real "
             "energy and a clear ask, or is limp and forgettable. You tolerate sharp, aggressive tone; you flag "
             "anything mealy-mouthed or off-message."),
    Reviewer("Hostile / opposition reader", "judge/gpt",
             "You are an opponent's tracker looking for ammunition. Judge what in this message could backfire, be "
             "clipped out of context, offend a group, or be attacked as false or extreme. Flag the liabilities."),
    Reviewer("Message-quality coach", "judge/sonnet",
             "You are a top political copy chief. Judge purely on craft: is this the BEST possible version of this "
             "message? Clarity, hook, single ask, memorability, structure, and length-fit for the channel. Always "
             "give one concrete way to make it better."),
    Reviewer("Compliance & legal guardrail", "judge/gemini",
             "You are a campaign lawyer. This is a guardrail, not the main goal: flag only missing/weak 'Paid for "
             "by' disclaimers, unverified factual or financial claims, and clear FEC/FCC/TCPA exposure."),
]


# ── the review JOBS, independent of which model performs them ───────────────────
@dataclass
class Job:
    """A review axis, decoupled from any model. Every simulation assigns each axis to
    a model, and the assignment ROTATES across simulations so that over a run every
    model scores every axis — bias-balanced diversity from the five-model council."""
    key: str
    name: str
    criteria: str
    role: str = "reward"  # "reward" (feeds the headline score) | "guardrail" (a gate/flag)


# The three things a campaign actually optimizes when it tailors a message to a group
# (the methodology the team settled on). Each message is scored FOR ITS TARGET SEGMENT —
# the council strengthens it for that group and never softens it to court non-recipients.
# Only the guardrail constrains. Edit freely in the Configure page; reviewers never rewrite.
DEFAULT_JOBS: list[Job] = [
    Job("power", "Message power",
        "Judge ONLY how strong and compelling this message is FOR THE TARGET SEGMENT it's written for — "
        "its hook, clarity, single clear ask, memorability, emotional pull, and persuasive force. A message "
        "built to hit hard for its target should score HIGH even if it would not appeal to other groups. Do "
        "NOT lower the score because it fails to court voters outside the target — that is the point of "
        "tailoring, not a flaw.", role="reward"),
    Job("tailoring", "Tailoring to the target",
        "Judge whether this message genuinely speaks to and resonates with THE SPECIFIC TARGET SEGMENT — their "
        "lives, language, values, and concerns — using what is broadly true of that group. Reward authentic, "
        "specific fit; flag generic copy that could go to anyone, AND flag lazy stereotype or pandering. Trust "
        "real resonance over a narrow data point. Do NOT reward softening or hedging the message to also appeal "
        "to people outside the target.", role="reward"),
    Job("guardrail", "Safety guardrail",
        "You are a guardrail, NOT a booster — do not score persuasion or fit (other reviewers do that). Flag "
        "ONLY genuine risk: anything heinous, offensive, hateful, or cringe; false or unverifiable claims; a "
        "missing/weak 'Paid for by'; and above all anything that, if it surfaced beyond the target audience, "
        "could be clipped and used against the campaign. A clean message scores high; a risky one scores low "
        "with the specific liability named.", role="guardrail"),
]


def rotate_reviewers(jobs: list[Job], models: list[str], offset: int) -> list[Reviewer]:
    """Assign each job a model, rotated by `offset`. With equal counts this is a
    bijection; over offsets 0..N-1 every model plays every job exactly once."""
    n = len(models) or 1
    return [Reviewer(job.name, models[(i + offset) % n], job.criteria, getattr(job, "role", "reward"))
            for i, job in enumerate(jobs)]


@dataclass
class MatrixConfig:
    channels: list[str] = field(default_factory=lambda: ["email", "sms"])
    intents: list[str] = field(default_factory=lambda: ["fresh_draft", "revision", "discussion"])
    repeats_per_cell: int = 1
    max_sims: int = 50            # ceiling on total SIMULATIONS (= drafts × rotations)
    max_drafts: int = 0           # ceiling on distinct Grok DRAFTS (0 → fall back to max_sims)
    rotations_per_draft: int = 1  # re-review each draft under N rotated model↔job assignments

    @property
    def draft_cap(self) -> int:
        return self.max_drafts or self.max_sims


@dataclass
class BudgetConfig:
    council_usd: float = 30.0          # informational overall ceiling (reviewers + council)
    backend_draft_usd: float = 15.0    # Grok drafting cap (backend)
    per_model_usd: float = 10.0        # HARD cap on EACH reviewer/council model


@dataclass
class DimensionCfg:
    enabled: bool = True
    severity: str | None = None  # override the default tier for this dimension


@dataclass
class RubricConfig:
    # deterministic length thresholds
    sms_max_chars: int = 320
    broadcast_slot_seconds: int = 30
    words_per_sec: float = 2.5
    speech_min_words: int = 120
    # platform stance-drift bands (0..1)
    stance_drift_warn: float = 0.50
    stance_drift_high: float = 0.75
    # per-dimension enable/severity overrides
    dimensions: dict[str, DimensionCfg] = field(default_factory=dict)

    def is_enabled(self, dimension: str) -> bool:
        cfg = self.dimensions.get(dimension)
        return cfg.enabled if cfg else True  # unknown dims (e.g. advisory:*) default on

    def override_severity(self, dimension: str) -> str | None:
        cfg = self.dimensions.get(dimension)
        return cfg.severity if cfg else None


@dataclass
class FlaggingConfig:
    cluster: bool = True
    min_severity: str = "low"  # low | medium | high | critical


@dataclass
class OutputConfig:
    db_path: str = "runs/harness.db"


@dataclass
class HarnessConfig:
    name: str = "unnamed"
    description: str = ""
    target: TargetConfig = field(default_factory=TargetConfig)
    council: CouncilConfig = field(default_factory=CouncilConfig)  # the 5-model council (generate + review)
    jobs: list[Job] = field(default_factory=lambda: list(DEFAULT_JOBS))  # the 5 review roles, rotated across models
    reviewers: list[Reviewer] = field(default_factory=lambda: list(DEFAULT_REVIEWERS))  # legacy fixed-model council
    matrix: MatrixConfig = field(default_factory=MatrixConfig)
    budgets: BudgetConfig = field(default_factory=BudgetConfig)
    rubric: RubricConfig = field(default_factory=RubricConfig)
    flagging: FlaggingConfig = field(default_factory=FlaggingConfig)
    output: OutputConfig = field(default_factory=OutputConfig)

    @property
    def cell_count(self) -> int:
        m = self.matrix
        cells = (len(self.council.models) * max(1, len(self.council.personas))
                 * len(m.channels) * len(m.intents) * m.repeats_per_cell)
        return min(cells, m.max_sims)

    @property
    def enabled_dimensions(self) -> list[str]:
        return [d for d, c in self.rubric.dimensions.items() if c.enabled]


def load_config(path: str | Path) -> HarnessConfig:
    d = tomllib.loads(Path(path).read_text())
    t, c = d.get("target", {}), d.get("council", {})
    m, b, r = d.get("matrix", {}), d.get("budgets", {}), d.get("rubric", {})
    reviewers = [Reviewer(rv.get("name", "Reviewer"), rv.get("model", "judge/sonnet"), rv.get("criteria", ""))
                 for rv in d.get("reviewers", [])] or list(DEFAULT_REVIEWERS)
    jobs = [Job(jb.get("key", jb.get("name", f"job{i}")), jb.get("name", "Reviewer"), jb.get("criteria", ""))
            for i, jb in enumerate(d.get("jobs", []))] or list(DEFAULT_JOBS)
    fl, o = d.get("flagging", {}), d.get("output", {})
    dims = {
        k: DimensionCfg(enabled=v.get("enabled", True), severity=v.get("severity"))
        for k, v in r.get("dimensions", {}).items()
    }
    return HarnessConfig(
        name=d.get("name", "unnamed"),
        description=d.get("description", ""),
        target=TargetConfig(
            base_url=t.get("base_url", "http://localhost:8000"),
            dev_email=t.get("dev_email", "harness-operator@example.com"),
            bearer_token=t.get("bearer_token", ""),
        ),
        council=CouncilConfig(models=c.get("models", CouncilConfig().models), personas=c.get("personas", [])),
        jobs=jobs,
        reviewers=reviewers,
        matrix=MatrixConfig(
            channels=m.get("channels", MatrixConfig().channels),
            intents=m.get("intents", MatrixConfig().intents),
            repeats_per_cell=m.get("repeats_per_cell", 1),
            max_sims=m.get("max_sims", 50),
            max_drafts=m.get("max_drafts", 0),
            rotations_per_draft=m.get("rotations_per_draft", 1),
        ),
        budgets=BudgetConfig(
            council_usd=b.get("council_usd", 30.0),
            backend_draft_usd=b.get("backend_draft_usd", 15.0),
            per_model_usd=b.get("per_model_usd", 10.0),
        ),
        rubric=RubricConfig(
            sms_max_chars=r.get("sms_max_chars", 320),
            broadcast_slot_seconds=r.get("broadcast_slot_seconds", 30),
            words_per_sec=r.get("words_per_sec", 2.5),
            speech_min_words=r.get("speech_min_words", 120),
            stance_drift_warn=r.get("stance_drift_warn", 0.50),
            stance_drift_high=r.get("stance_drift_high", 0.75),
            dimensions=dims,
        ),
        flagging=FlaggingConfig(cluster=fl.get("cluster", True), min_severity=fl.get("min_severity", "low")),
        output=OutputConfig(db_path=o.get("db_path", "runs/harness.db")),
    )
