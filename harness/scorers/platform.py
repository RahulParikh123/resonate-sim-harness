"""Layer 2 — platform-native signals.

Resonate already computes quality/safety signals and returns them on every draft.
Rather than re-derive them, the harness harvests them straight from the
draft-batch response: `stance_drift_score`, `advisory_flags`, `refused`.

(The in-process FEC/TCPA/FCC validators from backend/services/compliance/* can be
imported here for grading once the backend package is on the path — left as a hook.)
"""

from __future__ import annotations

from ..config import RubricConfig
from ..schemas import Finding, Severity, SimResult

# Map advisory_flags strings the backend may attach → severity.
_ADVISORY_SEVERITY = {
    "stance_drift": Severity.MEDIUM,
    "unverified_claim": Severity.HIGH,
    "unsourced_claim": Severity.HIGH,
    "compliance": Severity.HIGH,
    "compliance_block": Severity.HIGH,
    "messenger_low_confidence": Severity.LOW,
}


def score_platform(sim: SimResult, rubric: RubricConfig | None = None) -> list[Finding]:
    rubric = rubric or RubricConfig()
    out: list[Finding] = []

    if sim.stance_drift_score is not None:
        s = sim.stance_drift_score
        if s >= rubric.stance_drift_high:
            out.append(
                Finding("stance_drift", Severity.HIGH, False,
                        f"stance_drift_score={s:.2f} ≥ {rubric.stance_drift_high} — material drift from stated stance.",
                        source="platform")
            )
        elif s >= rubric.stance_drift_warn:
            out.append(
                Finding("stance_drift", Severity.MEDIUM, False,
                        f"stance_drift_score={s:.2f} ≥ {rubric.stance_drift_warn} — possible stance drift.",
                        source="platform")
            )

    for flag in sim.advisory_flags:
        sev = _ADVISORY_SEVERITY.get(flag, Severity.LOW)
        out.append(
            Finding(f"advisory:{flag}", sev, False, f"Backend attached advisory flag '{flag}'.", source="platform")
        )

    return out
