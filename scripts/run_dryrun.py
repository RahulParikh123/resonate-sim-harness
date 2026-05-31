#!/usr/bin/env python3
"""Full pipeline in DRY-RUN mode: score → flag → cluster → SQLite.

No keys, no backend. Proves the scoring+flagging+storage loop end-to-end and
shows the cluster-first triage view the reviewer will actually use.

    python3 scripts/run_dryrun.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness.runner import run_dryrun  # noqa: E402
from harness.schemas import Severity  # noqa: E402

ICON = {Severity.CRITICAL: "⛔", Severity.HIGH: "🔴", Severity.MEDIUM: "🟠", Severity.LOW: "🟡"}


def main() -> int:
    fixtures = ROOT / "fixtures" / "sample_drafts.json"
    db = ROOT / "runs" / "harness.db"
    run_id, verdicts, clusters = run_dryrun(fixtures, str(db))

    flagged = sum(1 for v in verdicts if not v.passed)
    print(f"\n  DRY RUN #{run_id}  ·  {len(verdicts)} sims  ·  {flagged} flagged  ·  saved → runs/harness.db")
    print("  Triage view — failure clusters ranked by severity × frequency:")
    print("  " + "─" * 66)
    for c in clusters:
        chans = ", ".join(f"{k}×{n}" for k, n in sorted(c.channels.items(), key=lambda kv: -kv[1]))
        ev = f'  e.g. "{c.example_evidence}"' if c.example_evidence else ""
        print(f"  {ICON[c.severity]} {c.severity.value.upper():<8} {c.dimension:<28} ×{c.size}  [{chans}]{ev}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
