#!/usr/bin/env python3
"""MVP-zero demo: run the deterministic scorer over sample drafts.

No keys, no backend, no install — just:  python3 scripts/demo_scorer.py
Proves the cheap-and-instant flagging layer before we wire the live council.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness.schemas import SimResult, Severity, severity_rank  # noqa: E402
from harness.scorers.deterministic import score_deterministic  # noqa: E402

ICON = {Severity.CRITICAL: "⛔", Severity.HIGH: "🔴", Severity.MEDIUM: "🟠", Severity.LOW: "🟡"}


def main() -> int:
    fixtures = json.loads((ROOT / "fixtures" / "sample_drafts.json").read_text())
    sims = [SimResult.from_dict(d) for d in fixtures]

    by_dim: Counter[str] = Counter()
    by_sev: Counter[str] = Counter()
    flagged = 0

    print(f"\n  Resonate sim-harness · deterministic scorer")
    print(f"  {len(sims)} sample drafts · zero keys · zero backend")
    print("  " + "─" * 66)

    for sim in sims:
        findings = score_deterministic(sim)
        tag = f"{sim.channel} · {sim.intent_type}"
        if not findings:
            print(f"\n  ✅ [{sim.id}]  {tag}  — clean")
            continue
        flagged += 1
        worst = max(findings, key=lambda f: severity_rank(f.severity))
        print(f"\n  {ICON[worst.severity]} [{sim.id}]  {tag}  — {len(findings)} flag(s)")
        for f in sorted(findings, key=lambda f: -severity_rank(f.severity)):
            ev = f'  →  "{f.evidence}"' if f.evidence else ""
            print(f"      {ICON[f.severity]} {f.severity.value.upper():<8} {f.dimension}{ev}")
            print(f"         {f.detail}")
            by_dim[f.dimension] += 1
            by_sev[f.severity.value] += 1

    print("\n  " + "─" * 66)
    print(f"  {flagged}/{len(sims)} drafts flagged · {sum(by_dim.values())} findings")
    if by_sev:
        sev_line = "   ".join(f"{ICON[Severity(s)]} {n} {s}" for s, n in by_sev.most_common())
        print(f"  by severity:  {sev_line}")
    print("  by dimension:")
    for dim, n in by_dim.most_common():
        print(f"      {n:>3}  {dim}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
