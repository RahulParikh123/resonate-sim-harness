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
    models: list[str] = field(default_factory=lambda: ["council/claude", "council/gpt"])
    personas: list[str] = field(default_factory=list)


@dataclass
class Reviewer:
    """A critic persona. A model role-plays this reviewer and judges Grok's draft
    against `criteria` — its own standards/preferences. It never rewrites the draft."""
    name: str
    model: str
    criteria: str


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


@dataclass
class MatrixConfig:
    channels: list[str] = field(default_factory=lambda: ["email", "sms"])
    intents: list[str] = field(default_factory=lambda: ["fresh_draft", "revision", "discussion"])
    repeats_per_cell: int = 1
    max_sims: int = 50


@dataclass
class BudgetConfig:
    council_usd: float = 30.0
    backend_draft_usd: float = 15.0


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
    council: CouncilConfig = field(default_factory=CouncilConfig)  # generates varied campaign INPUTS
    reviewers: list[Reviewer] = field(default_factory=lambda: list(DEFAULT_REVIEWERS))  # the review council
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
        reviewers=reviewers,
        matrix=MatrixConfig(
            channels=m.get("channels", MatrixConfig().channels),
            intents=m.get("intents", MatrixConfig().intents),
            repeats_per_cell=m.get("repeats_per_cell", 1),
            max_sims=m.get("max_sims", 50),
        ),
        budgets=BudgetConfig(
            council_usd=b.get("council_usd", 30.0),
            backend_draft_usd=b.get("backend_draft_usd", 15.0),
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
