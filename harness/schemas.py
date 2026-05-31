"""Core data shapes for the Resonate simulation harness.

Kept dependency-free (stdlib dataclasses) so the deterministic scorer + demo
run with a bare `python3` — no install, no keys, no backend. The council /
judge / api-client layers (added next) will introduce pydantic + httpx +
litellm, but the scoring engine deliberately stays importable on its own.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


_SEV_ORDER = {Severity.CRITICAL: 4, Severity.HIGH: 3, Severity.MEDIUM: 2, Severity.LOW: 1}


def severity_rank(s: Severity) -> int:
    return _SEV_ORDER.get(s, 0)


@dataclass
class Finding:
    """One scored dimension. `passed=False` means it is a flag to surface."""

    dimension: str
    severity: Severity
    passed: bool
    detail: str
    evidence: str | None = None
    source: str = "deterministic"  # deterministic | platform | judge


@dataclass
class SimResult:
    """A captured platform output to be scored.

    In the MVP-zero demo these come from `fixtures/sample_drafts.json`; once the
    live driver is wired they come straight from a Resonate
    `language/draft-batch` response (content_text, refused, advisory_flags,
    stance_drift_score) plus the originating operator brief.
    """

    id: str
    channel: str  # live UI channel ("Speeches / Docs", "TV", …) or backend family
    intent_type: str = "fresh_draft"  # fresh_draft | revision | discussion | edge_case
    surface: str = ""  # which chatbox/surface produced this (e.g. "Uniform Messaging — Email")
    model: str = ""    # input-generator model (incidental; the platform always drafts with Grok)
    persona: str = ""  # input-generator persona (incidental)
    content_text: str = ""
    subject: str | None = None
    brief_intent: str = ""
    brief_context: str = ""  # operator-supplied facts/URLs the draft may legitimately use
    # The clarifying questions the platform asked before drafting, and the answers given.
    preflight_qa: list = field(default_factory=list)  # [{"q": ..., "a": ...}, …]
    refused: bool = False
    produced_composer_draft: bool = True  # did a draft actually land in the composer?
    advisory_flags: list[str] = field(default_factory=list)
    stance_drift_score: float | None = None
    # Filled by the review council (live mode): [{reviewer, score, verdict, concern, improve}, …]
    reviews: list = field(default_factory=list)
    quality_score: float | None = None  # aggregate of reviewer scores, 0–100

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SimResult":
        return cls(
            id=str(d.get("id", "?")),
            channel=d.get("channel", ""),
            intent_type=d.get("intent_type", "fresh_draft"),
            surface=d.get("surface", ""),
            model=d.get("model", ""),
            persona=d.get("persona", ""),
            content_text=d.get("content_text", ""),
            subject=d.get("subject"),
            brief_intent=d.get("brief_intent", ""),
            brief_context=d.get("brief_context", ""),
            preflight_qa=list(d.get("preflight_qa") or []),
            refused=bool(d.get("refused", False)),
            produced_composer_draft=bool(d.get("produced_composer_draft", True)),
            advisory_flags=list(d.get("advisory_flags") or []),
            stance_drift_score=d.get("stance_drift_score"),
            reviews=list(d.get("reviews") or []),
            quality_score=d.get("quality_score"),
        )
