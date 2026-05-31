"""Human-readable labels — turn internal keys into plain English for any UI.

Storage and code keep the short keys (stable, greppable); every place a person
reads is routed through here so nobody sees machine vernacular.
"""

from __future__ import annotations

# dimension key → (short plain-English label, one full-sentence explanation)
DIMENSION = {
    "scaffolding_leak": (
        "Leftover template placeholders",
        "A draft reached the editor with template scaffolding still in it — like “[CLAIM NEEDS SOURCE]” "
        "or “[INSERT NAME]” — instead of finished text."),
    "empty_or_refused": (
        "Empty or refused draft",
        "The model returned nothing, or refused a perfectly ordinary request."),
    "fabricated_operational_info": (
        "Made-up links, phone numbers, or event details",
        "The draft invented a website link, phone number, or RSVP/event detail that the operator never provided."),
    "chat_routing": (
        "Changed the draft when only asked to chat",
        "The operator asked for feedback in the chat and said not to change anything — but the system rewrote "
        "the draft anyway."),
    "length_contract": (
        "Wrong length for the channel",
        "The message doesn’t fit its format — for example an SMS over the character limit, or a TV/radio script "
        "that runs past its time slot."),
    "markdown_in_plaintext": (
        "Formatting symbols showing as raw text",
        "Symbols like ** or ## appear as literal characters in a channel that should be plain text, such as an SMS."),
    "compliance_phrasing": (
        "Missing or weak legal disclaimer",
        "The legally required “Paid for by …” disclaimer is missing, or uses soft wording instead of the strict form."),
    "stance_drift": (
        "Drifted off the candidate’s position",
        "The draft moved away from the candidate’s stated positions."),
    "persuasiveness": (
        "Not persuasive for this audience",
        "The AI judges felt the message wouldn’t land with the voters it was aimed at."),
    "voice_fidelity": (
        "Off-voice or generic politician-speak",
        "The draft doesn’t sound like the candidate, or leans on clichés."),
    "factual_integrity": (
        "Unsupported factual claims",
        "Specific claims — numbers, money, voting records — are stated as fact without any source."),
    "stance_fidelity": (
        "Didn’t hold the requested position or tone",
        "The draft strays from the position or tone the operator asked for."),
    "reviewer_concern": (
        "Flagged by a reviewer’s standards",
        "One of the review personas judged Grok’s draft against its own standards — tone, rhetoric, risk "
        "tolerance, or staying on-message — and raised a concern. Different reviewers hold different standards, "
        "so a split is expected and informative."),
}

_SOURCE = {"deterministic": "rule check", "platform": "platform signal", "judge": "AI judge"}
_MODEL = {
    "council/claude": "Claude", "council/gpt": "GPT", "council/gemini": "Gemini",
    "council/kimi": "Kimi", "council/grok": "Grok",
    "judge/sonnet": "Claude Sonnet (judge)", "judge/gpt": "GPT (judge)", "judge/gemini": "Gemini (judge)",
}
_CHANNEL = {
    "email": "Email", "sms": "SMS", "speech": "Speech / long-form", "mail": "Mail",
    "radio": "Radio", "tv": "TV", "social": "Social media", "press": "Press / long-form", "canvass": "Canvass",
}
_INTENT = {
    "fresh_draft": "Fresh draft", "revision": "Revision",
    "discussion": "Discussion (chat only)", "edge_case": "Edge case",
}


def label(dim: str) -> str:
    if dim.endswith(":disagreement"):
        base = dim[: -len(":disagreement")]
        return f"Judges split on “{DIMENSION.get(base, (base.replace('_', ' '), ''))[0]}”"
    return DIMENSION.get(dim, (dim.replace("_", " ").capitalize(), ""))[0]


def describe(dim: str) -> str:
    if dim.endswith(":disagreement"):
        return "The AI judges disagreed on this draft — worth a human look, and the best material for tuning the rubric."
    return DIMENSION.get(dim, ("", ""))[1]


def humanize_source(s: str) -> str:
    return _SOURCE.get(s, s)


def humanize_model(m: str) -> str:
    return _MODEL.get(m, (m.split("/")[-1].title() if m else "—")) or "—"


def humanize_channel(c: str) -> str:
    return _CHANNEL.get((c or "").strip().lower(), c or "—")


def humanize_intent(i: str) -> str:
    return _INTENT.get(i, (i or "").replace("_", " ").capitalize() or "—")


_SEVERITY = {
    "pass": ("✅", "Clean"), "critical": ("⛔", "Critical"), "high": ("🔴", "Serious"),
    "medium": ("🟠", "Moderate"), "low": ("🟡", "Minor"),
}
_MODE = {"dryrun": "sample run", "live": "live run"}


def humanize_severity(s: str) -> str:
    emoji, word = _SEVERITY.get(s, ("", s or "—"))
    return f"{emoji} {word}".strip()


def humanize_mode(m: str) -> str:
    return _MODE.get(m, (m or "").replace("_", " ").capitalize() or "run")


def humanize_message_id(sid: str) -> str:
    """Turn an internal id (sim-3, email-clean) into something a person reads."""
    if not sid:
        return "—"
    if sid.startswith("sim-") and sid[4:].isdigit():
        return f"Message {int(sid[4:]) + 1}"
    return sid.replace("-", " ").replace("_", " ").title()
