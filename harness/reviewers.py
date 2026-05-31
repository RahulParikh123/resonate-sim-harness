"""The review council — diverse models, each PROXYING a point of view (mostly the
voters a message is trying to reach), judging the draft Grok produced.

Reviewers REVIEW; they never rewrite. Each one judges broadly — not just the final
text, but whether the platform asked the right questions and gathered the right
context — and answers the overriding question: is this the BEST possible message
for my point of view, and if not, how should it improve? Each returns a 0–100
score (reward), an optional concern (risk), and one concrete improvement.
"""

from __future__ import annotations

import asyncio

from .config import Reviewer
from .llm import Budget, acomplete, safe_json
from .schemas import Finding, Severity, SimResult

REVIEW_DIMENSION = "reviewer_concern"
_VERDICT_SEVERITY = {"fail": Severity.HIGH, "concern": Severity.MEDIUM, "meets": None}


def _system(rv: Reviewer) -> str:
    return (
        f'You are "{rv.name}", a reviewer on a campaign-messaging QA panel. You PROXY this point of view:\n'
        f"{rv.criteria}\n\n"
        "You do NOT rewrite, redraft, or write replacement copy — you only review and score.\n"
        "Judge BROADLY, not narrowly: weigh the final draft AND whether the platform asked the right "
        "clarifying questions and gathered the right context to make this the best possible message for your "
        "point of view. Do not assume the questions it asked were the right ones.\n"
        "GROUND your score in the platform's OWN signals shown below — its stance-drift score, the advisory "
        "flags it raised, and its recommended messengers. These are exactly what Resonate itself grades a draft "
        "on. A high stance-drift score or a high-severity advisory flag MUST pull your score down even if the "
        "copy reads well; clean signals support a higher score. Combine those signals with your point of view.\n"
        "Your overriding question: from your point of view, is this the BEST possible message — and if not, "
        "how should it improve?\n"
        'Return ONLY strict JSON: {"score": <integer 0-100, how good this message is for your POV>, '
        '"verdict": "meets" | "concern" | "fail", "concern": "<one sentence on any real risk or problem, or '
        'empty>", "improve": "<one concrete, specific way to make it better for your POV>"}'
    )


def _format_qa(sim: SimResult) -> str:
    if not sim.preflight_qa:
        return "(the platform asked NO clarifying questions before drafting — judge whether it should have)"
    return "\n".join(f"  Q: {qa.get('q', '')}\n  A: {qa.get('a', '')}" for qa in sim.preflight_qa)


def _platform_signals(sim: SimResult) -> str:
    """The platform's OWN scoring signals for this draft — what Resonate itself grades on.
    Reviewers must ground their score in these, not just taste."""
    lines: list[str] = []
    if sim.stance_drift_score is not None:
        how = f", via {sim.stance_drift_method}" if sim.stance_drift_method else ""
        lines.append(f"- Stance-drift score: {sim.stance_drift_score:.2f} on a 0–1 scale{how} "
                     "(0 = perfectly on the campaign's stated stance, 1 = badly off it).")
    flags = []
    for f in sim.advisory_flags or []:
        if isinstance(f, dict):
            code = f.get("code") or f.get("type") or "flag"
            sev = f" [{f.get('severity')}]" if f.get("severity") else ""
            note = f": {f.get('note') or f.get('detail')}" if (f.get("note") or f.get("detail")) else ""
            flags.append(f"{code}{sev}{note}")
        elif str(f).strip():
            flags.append(str(f))
    lines.append("- Platform advisory flags raised: " + ("; ".join(flags) if flags else "none") + ".")
    if sim.messenger_recommendation:
        names = []
        for m in sim.messenger_recommendation[:5]:
            if isinstance(m, dict):
                names.append(str(m.get("name") or m.get("surrogate") or m.get("messenger") or m.get("id") or "messenger"))
            else:
                names.append(str(m))
        lines.append("- Recommended messengers (the platform's surrogate-fit signal): " + ", ".join(names) + ".")
    return "\n".join(lines) if lines else "(no platform signals were returned for this draft)"


def _user(sim: SimResult) -> str:
    spoken = " (a SPEECH — judge it as it would sound read aloud, in the speech's context)" \
        if sim.channel.lower() in ("speech", "speeches / docs", "press") else ""
    return (
        f"Channel: {sim.channel}{spoken}\n"
        f"What the campaign originally asked for: {sim.brief_intent}\n\n"
        f"Clarifying questions the platform asked, and the answers it got:\n{_format_qa(sim)}\n\n"
        f"Facts the operator supplied: {sim.brief_context or 'none'}\n\n"
        f"The draft Grok produced:\n{sim.content_text}\n\n"
        f"The platform's own signals for this draft (what Resonate grades on):\n{_platform_signals(sim)}\n\n"
        "Review and score it from your point of view, grounded in those platform signals."
    )


def _clip(score) -> int | None:
    try:
        return max(0, min(100, int(round(float(score)))))
    except (TypeError, ValueError):
        return None


async def review_draft(sim: SimResult, reviewers: list[Reviewer], budget: Budget | None = None) -> list[dict]:
    """Run every reviewer over Grok's draft. Returns one review record per reviewer:
    {reviewer, score, verdict, concern, improve}."""
    if not (sim.content_text or "").strip():
        return []

    async def one(rv: Reviewer):
        try:
            text, _ = await acomplete(rv.model, _system(rv), _user(sim), budget=budget, json_mode=True, temperature=0.2)
            d = safe_json(text) or {}
            return {
                "reviewer": rv.name,          # the JOB (point of view)
                "model": rv.model,            # the MODEL that played it this simulation
                "score": _clip(d.get("score")),
                "verdict": str(d.get("verdict", "meets")).lower(),
                "concern": (d.get("concern") or "").strip(),
                "improve": (d.get("improve") or "").strip(),
            }
        except Exception:
            return None

    return [r for r in await asyncio.gather(*[one(rv) for rv in reviewers]) if r]


def reviews_to_findings(reviews: list[dict]) -> list[Finding]:
    """Turn reviewer concerns/fails into flags for the triage view (the punishment side)."""
    out: list[Finding] = []
    for r in reviews:
        sev = _VERDICT_SEVERITY.get(r.get("verdict", "meets"))
        if sev is None:
            continue
        out.append(Finding(REVIEW_DIMENSION, sev, False,
                           f"{r['reviewer']}: {r.get('concern') or 'raised a concern'}", source=r["reviewer"]))
    return out


def aggregate_quality(reviews: list[dict]) -> float | None:
    """Mean of reviewer scores, 0–100 (the reward side)."""
    scores = [r["score"] for r in reviews if isinstance(r.get("score"), (int, float))]
    return round(sum(scores) / len(scores), 1) if scores else None
