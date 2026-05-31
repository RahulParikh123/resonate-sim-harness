#!/usr/bin/env python3
"""Config-driven harness run.

    python3 scripts/run.py --config configs/example.harness.toml

Prints the config (the human gates) so a run is self-documenting, then executes.
Until backend + keys are wired, it runs in DRY-RUN mode against fixtures so the
config, rubric, and per-model / per-persona breakdowns are fully exercisable today.
For a live run against the backend, use scripts/run_live.py.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness.config import load_config  # noqa: E402
from harness.labels import humanize_model  # noqa: E402
from harness.report import print_breakdowns, print_clusters, print_legend  # noqa: E402
from harness.runner import run_with_config  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, help="path to a harness .toml config")
    ap.add_argument("--fixtures", default=str(ROOT / "fixtures" / "sample_drafts.json"))
    args = ap.parse_args()

    cfg = load_config(args.config)

    print(f"\n  ╭─ {cfg.name} " + "─" * max(0, 60 - len(cfg.name)))
    print(f"  │ {cfg.description}")
    print(f"  │ target    {cfg.target.base_url}  (dev: {cfg.target.dev_email})")
    print(f"  │ drafts    by Grok (the platform backend — unchanged)")
    print(f"  │ reviewers {', '.join(rv.name for rv in cfg.reviewers)}")
    print(f"  │ matrix    {len(cfg.matrix.channels)} channels × {len(cfg.matrix.intents)} intents → {cfg.cell_count} sims (cap {cfg.matrix.max_sims})")
    print(f"  │ budgets   reviewers+inputs ${cfg.budgets.council_usd:.0f} · Grok drafting ${cfg.budgets.backend_draft_usd:.0f}")
    print(f"  │ checks    {len(cfg.enabled_dimensions)} objective rule checks + {len(cfg.reviewers)} reviewers")
    print(f"  ╰" + "─" * 68)
    print("  MODE: dry-run (objective checks on fixtures). Live reviewers wire in via run_live.py --review once keys are set.")

    run_id, verdicts, clusters = run_with_config(cfg, args.fixtures)
    flagged = sum(1 for v in verdicts if not v.passed)
    print(f"\n  RUN #{run_id} · {len(verdicts)} sims · {flagged} flagged · saved → {cfg.output.db_path}\n")
    print_clusters(clusters)
    print_breakdowns(verdicts)
    print_legend()
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
