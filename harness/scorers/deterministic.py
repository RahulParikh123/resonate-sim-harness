"""Layer 1 — deterministic checks. Pure stdlib, zero LLM, runs on every draft.

These are the cheapest and highest-confidence flags: hard pattern failures the
Resonate operators have repeatedly hit (per the repo's HANDOFF.md + factual_grounding.py).
Anything caught here is decisive and skips the expensive judge panel entirely.

Mirrors the intent of backend/src/resonate/services/factual_grounding.py and the
channel length contracts the language agent enforces for TV/radio.
"""

from __future__ import annotations

import re

from ..config import RubricConfig
from ..schemas import Finding, Severity, SimResult

# --- pattern banks --------------------------------------------------------
_SCAFFOLD_RE = re.compile(
    r"\[\s*(?:CLAIM\s+NEEDS\s+SOURCE|NEEDS\s+SOURCE|NEEDS\s+INFO|INSERT|TODO|TBD|FILL\s+IN|PLACEHOLDER)\b[^\]]*\]",
    re.IGNORECASE,
)
_INSTRUCTION_HEADER_RE = re.compile(r"^\s{0,3}#{1,6}\s*instructions?\s*:", re.IGNORECASE | re.MULTILINE)
# generic ALL-CAPS bracket fill-ins: [CANDIDATE NAME], [CITY], [DATE], [EVENT]
_GENERIC_PLACEHOLDER_RE = re.compile(r"\[[A-Z][A-Z0-9 _/\-]{2,}\]")
_MARKDOWN_ORNAMENT_RE = re.compile(r"(\*\*[^*\n]+\*\*|__[^_\n]+__|~~[^~\n]+~~|^\s{0,3}#{1,6}\s)", re.MULTILINE)
_URL_RE = re.compile(r"https?://[^\s)\]>\"']+", re.IGNORECASE)
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}(?!\d)")
_SOFT_PAID_RE = re.compile(r"\bwe(?:'re|\s+are)\s+paid\s+for\s+by\b", re.IGNORECASE)
_PAID_FOR_BY_RE = re.compile(r"\bpaid\s+for\s+by\b", re.IGNORECASE)

# --- channel model --------------------------------------------------------
# Maps the 7 live UI channels onto normalized families used by the contracts.
CHANNEL_ALIASES = {
    "speeches / docs": "speech", "speeches/docs": "speech", "speech": "speech",
    "docs": "speech", "press": "speech",
    "email": "email", "sms": "sms", "mail": "mail",
    "radio": "radio", "tv": "tv",
    "social media": "social", "social": "social", "canvass": "canvass",
}
PAID_POLITICAL = {"email", "sms", "mail", "radio", "tv"}
PLAINTEXT_CHANNELS = {"sms", "social"}
# Length thresholds (SMS chars, broadcast slot, words/sec, speech min) live in RubricConfig.


def _norm_channel(ch: str) -> str:
    return CHANNEL_ALIASES.get(ch.strip().lower(), ch.strip().lower())


def _wc(text: str) -> int:
    return len(text.split())


def _short(s: str, n: int = 70) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1] + "…"


def _inside_needs_placeholder(text: str, token: str) -> bool:
    """True if `token` sits inside a [NEEDS INFO …] style bracket (i.e. grounded-as-missing)."""
    idx = text.find(token)
    if idx == -1:
        return False
    lb, rb = text.rfind("[", 0, idx), text.find("]", idx)
    return lb != -1 and rb != -1 and "NEEDS" in text[lb : rb + 1].upper()


# --- the engine -----------------------------------------------------------
def score_deterministic(sim: SimResult, rubric: RubricConfig | None = None) -> list[Finding]:
    """Return the list of FLAGS (failed findings) for one draft. Empty == clean.

    `rubric` supplies numeric thresholds. Dimension enable/disable + severity
    overrides are applied by the runner (apply_rubric), not here."""
    rubric = rubric or RubricConfig()
    text = sim.content_text or ""
    ch = _norm_channel(sim.channel)
    is_discussion = sim.intent_type == "discussion"
    out: list[Finding] = []

    # 1. empty / refused on a benign brief
    if sim.refused:
        out.append(Finding("empty_or_refused", Severity.HIGH, False, "Draft refused on a benign brief."))
    elif not text.strip() and not is_discussion:
        out.append(Finding("empty_or_refused", Severity.HIGH, False, "Draft is empty."))

    # 2. scaffolding / placeholder leakage  (top operator pain point)
    m = _SCAFFOLD_RE.search(text) or _INSTRUCTION_HEADER_RE.search(text) or _GENERIC_PLACEHOLDER_RE.search(text)
    if m:
        out.append(
            Finding("scaffolding_leak", Severity.HIGH, False,
                    "Template scaffolding/placeholder leaked into voter-facing copy.",
                    evidence=_short(m.group(0), 60))
        )

    # 3. raw markdown ornaments in plain-text channels
    if ch in PLAINTEXT_CHANNELS:
        mo = _MARKDOWN_ORNAMENT_RE.search(text)
        if mo:
            out.append(
                Finding("markdown_in_plaintext", Severity.MEDIUM, False,
                        f"Raw markdown ornament in a plain-text channel ({ch}).",
                        evidence=_short(mo.group(0), 30))
            )

    # 4. fabricated operational info — URLs / phones not grounded in the brief
    ctx = f"{sim.brief_context} {sim.brief_intent}"
    for rx, kind in ((_URL_RE, "URL"), (_PHONE_RE, "phone number")):
        for hit in rx.findall(text):
            hit = hit.rstrip(".,;:!?")
            if hit not in ctx and not _inside_needs_placeholder(text, hit):
                out.append(
                    Finding("fabricated_operational_info", Severity.HIGH, False,
                            f"{kind} not present in the operator brief and not placeholdered as [NEEDS INFO].",
                            evidence=_short(hit, 60))
                )
                break  # one per kind is enough to flag

    # 5. chat-routing violation — discussion intent must NOT emit a composer draft
    if is_discussion and sim.produced_composer_draft:
        out.append(
            Finding("chat_routing", Severity.HIGH, False,
                    "Chat-only (discussion) request wrongly produced a composer draft.")
        )

    # Draft-only checks below — skip for discussion turns (not a paid message).
    if is_discussion:
        return out

    # 6. channel length / format contract
    out.extend(_length_contract(sim, ch, text, rubric))

    # 7. compliance phrasing (cheap layer; full FEC/TCPA/FCC lives in the platform-signal scorer)
    if _SOFT_PAID_RE.search(text):
        out.append(
            Finding("compliance_phrasing", Severity.MEDIUM, False,
                    "Soft disclaimer phrasing — FEC requires the strict form 'Paid for by …'.",
                    evidence="we're paid for by")
        )
    elif ch in PAID_POLITICAL and text.strip() and not _PAID_FOR_BY_RE.search(text):
        out.append(
            Finding("compliance_phrasing", Severity.MEDIUM, False,
                    f"No 'Paid for by' disclaimer on a paid-political channel ({ch}).")
        )

    return out


def _length_contract(sim: SimResult, ch: str, text: str, rubric: RubricConfig) -> list[Finding]:
    findings: list[Finding] = []
    wc = _wc(text)

    if ch == "sms":
        if len(text) > rubric.sms_max_chars:
            findings.append(
                Finding("length_contract", Severity.MEDIUM, False,
                        f"SMS is {len(text)} chars (>{rubric.sms_max_chars} — multi-segment / likely to truncate).")
            )
    elif ch in ("radio", "tv"):
        max_words = int(rubric.broadcast_slot_seconds * rubric.words_per_sec)
        if wc > int(max_words * 1.1):
            est = wc / rubric.words_per_sec
            findings.append(
                Finding("length_contract", Severity.HIGH, False,
                        f"{ch.upper()} script ~{wc} words ≈ {est:.0f}s read — over the "
                        f":{rubric.broadcast_slot_seconds} slot (unusable on air).")
            )
    elif ch == "speech":
        if 0 < wc < rubric.speech_min_words:
            findings.append(
                Finding("length_contract", Severity.LOW, False,
                        f"Speech draft is only {wc} words — short for an opening/body/closing arc.")
            )

    if ch in ("email", "mail") and not (sim.subject or "").strip():
        findings.append(
            Finding("length_contract", Severity.MEDIUM, False, f"{ch.capitalize()} draft has no subject line.")
        )

    return findings
