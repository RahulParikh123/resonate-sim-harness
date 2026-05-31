"""The review council — five models rotating across three scoring AXES, judging the
draft Grok produced FOR ITS TARGET SEGMENT.

The axes (the methodology the team settled on):
  1. Message power — how strong/compelling the message is for its target.
  2. Tailoring to the target — does it genuinely land for that specific group.
  3. Safety guardrail — heinous / cringe / usable-against-you-if-it-leaks.

(1) and (2) are REWARD axes: strengthen the message for its target, never soften it to
court non-recipients — they feed the headline score. (3) is a GATE: a safety problem
caps the score no matter how good the copy reads. Reviewers REVIEW; they never rewrite.
Each returns a 0–100 score on its axis, a verdict, an optional concern, and one concrete
improvement, grounded in the platform's own signals.
"""

from __future__ import annotations

import asyncio

from .config import Reviewer
from .llm import Budget, acomplete, safe_json
from .schemas import Finding, Severity, SimResult

REVIEW_DIMENSION = "reviewer_concern"
_VERDICT_SEVERITY = {"fail": Severity.HIGH, "concern": Severity.MEDIUM, "meets": None}


def _system(rv: Reviewer) -> str:
    guard = getattr(rv, "role", "reward") == "guardrail"
    principle = (
        "As the guardrail you DO weigh broad blowback: judge how this could read to ANYONE — opponents, the "
        "press, other groups — because any message can leak. Score down real liabilities; a clean message "
        "scores high.\n" if guard else
        "A campaign deliberately makes a message hit hard for its TARGET and does NOT soften it to appeal to "
        "people who will never receive it. Do not lower the score just because it wouldn't land for other "
        "groups — that is correct tailoring, not a flaw.\n"
    )
    return (
        f'You are the "{rv.name}" reviewer on a campaign-messaging QA panel. You score exactly ONE axis:\n'
        f"{rv.criteria}\n\n"
        "You do NOT rewrite or redraft — you only review and score, and you stay strictly on YOUR axis "
        "(other reviewers cover the rest).\n"
        "This message is tailored to a SPECIFIC TARGET SEGMENT, named below — judge it FOR THAT SEGMENT.\n"
        + principle +
        "Factor in the platform's OWN signals shown below (stance-drift score, advisory flags, recommended "
        "messengers) — what Resonate itself grades on — alongside your axis.\n"
        'Return ONLY strict JSON: {"score": <integer 0-100 on your axis>, "verdict": "meets" | "concern" | '
        '"fail", "concern": "<one sentence naming any real problem on your axis, or empty>", '
        '"improve": "<one concrete, specific way to make it better on your axis>"}'
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
    seg = sim.target_segment or "the campaign's general audience (a uniform message to everyone)"
    return (
        f"TARGET SEGMENT — score the message FOR this group: {seg}\n"
        f"Channel: {sim.channel}{spoken}\n"
        f"What the campaign originally asked for: {sim.brief_intent}\n\n"
        f"Clarifying questions the platform asked, and the answers it got:\n{_format_qa(sim)}\n\n"
        f"Facts the operator supplied: {sim.brief_context or 'none'}\n\n"
        f"The draft Grok produced:\n{sim.content_text}\n\n"
        f"The platform's own signals for this draft (what Resonate grades on):\n{_platform_signals(sim)}\n\n"
        "Score it on your axis, for the target segment, grounded in those platform signals."
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
                "reviewer": rv.name,          # the AXIS (power / tailoring / guardrail)
                "model": rv.model,            # the MODEL that scored it this simulation
                "role": getattr(rv, "role", "reward"),  # reward (feeds headline) | guardrail (gate)
                "score": _clip(d.get("score")),
                "verdict": str(d.get("verdict", "meets")).lower(),
                "concern": (d.get("concern") or "").strip(),
                "improve": (d.get("improve") or "").strip(),
            }
        except Exception:
            return None

    return [r for r in await asyncio.gather(*[one(rv) for rv in reviewers]) if r]


def reviews_to_findings(reviews: list[dict]) -> list[Finding]:
    """Only the GUARDRAIL axis produces a flag — that's the real ship-blocker (a safety/
    backfire risk). The reward axes (power, tailoring) drive the quality SCORE, not flags:
    a merely weak-but-safe message is low-scoring, not 'flagged.' This keeps the flagged
    set to the genuinely serious minority instead of nearly every draft."""
    out: list[Finding] = []
    for r in reviews:
        if r.get("role") != "guardrail":
            continue
        verdict = r.get("verdict", "meets")
        if verdict == "fail":
            sev = Severity.CRITICAL
        elif verdict == "concern":
            sev = Severity.MEDIUM  # a soft concern is a note, not a flag
        else:
            continue
        out.append(Finding(REVIEW_DIMENSION, sev, False,
                           f"Safety guardrail: {r.get('concern') or 'flagged a risk'}", source=r["reviewer"]))
    return out


def aggregate_quality(reviews: list[dict]) -> float | None:
    """Headline 0–100 = mean of the REWARD axes (message power + tailoring). The guardrail
    is a GATE, not an average: a safety fail/concern caps the headline regardless of how
    strong or well-tailored the copy is — you can't buy back a liability with good writing."""
    rewards = [r["score"] for r in reviews
               if r.get("role", "reward") != "guardrail" and isinstance(r.get("score"), (int, float))]
    if rewards:
        base = sum(rewards) / len(rewards)
    else:  # guardrail-only / legacy reviews → fall back to any numeric score
        any_scores = [r["score"] for r in reviews if isinstance(r.get("score"), (int, float))]
        if not any_scores:
            return None
        base = sum(any_scores) / len(any_scores)
    for r in reviews:
        if r.get("role") == "guardrail":
            if r.get("verdict") == "fail":
                base = min(base, 35.0)
            elif r.get("verdict") == "concern":
                base = min(base, 60.0)
    return round(base, 1)
