#!/usr/bin/env python3
"""Re-score a finished run from cached drafts + stored reviews — NO new LLM calls.

Applies the CURRENT scoring/flagging rules and re-attaches the draft text, then saves a
new run. Use after changing flagging logic so you don't pay to re-draft. Drafts come from
runs/drafts-<config>.json (written by run_live); reviews come from the stored run.

    <venv>/bin/python scripts/reprocess.py --config configs/thousands.toml [--run N] [--publish]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness.config import load_config  # noqa: E402
from harness.flagging import cluster_findings  # noqa: E402
from harness.runner import score_sim  # noqa: E402
from harness.schemas import SimResult  # noqa: E402
from harness.store import Store  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--run", type=int, default=0, help="run id to reprocess (default: latest)")
    ap.add_argument("--publish", action="store_true")
    args = ap.parse_args()

    cfg = load_config(args.config)
    store = Store(cfg.output.db_path)
    runs = store.list_runs()
    if not runs:
        print("no runs found")
        return 1
    run = next((r for r in runs if r["id"] == args.run), None) if args.run else max(runs, key=lambda r: r["id"])
    if run is None:
        print(f"run {args.run} not found")
        return 1
    sims = store.sims_for_run(run["id"])

    cache_path = ROOT / "runs" / f"drafts-{cfg.name}.json"
    cache = {}
    if cache_path.exists():
        for d in json.loads(cache_path.read_text()):
            cache[d.get("id")] = d
    print(f"reprocessing run {run['id']} ({len(sims)} sims) · {len(cache)} cached drafts with text")

    verdicts = []
    for s in sims:
        sid = s["sim_id"]
        draft = cache.get(sid.rsplit("-r", 1)[0], {})
        sim = SimResult(
            id=sid, channel=s.get("channel", ""), intent_type=s.get("intent_type", "fresh_draft"),
            surface=s.get("surface", ""), target_segment=s.get("target_segment", ""),
            content_text=draft.get("content_text", ""), brief_intent=draft.get("brief_intent", ""),
            brief_context=draft.get("brief_context", ""),
            advisory_flags=draft.get("advisory_flags", []) or [],
            stance_drift_score=draft.get("stance_drift_score"),
            preflight_qa=draft.get("preflight_qa", []) or [],
            reviews=json.loads(s.get("reviews_json") or "[]"),
            quality_score=s.get("quality_score"),
            model=s.get("model", ""), persona=s.get("persona", ""),
        )
        verdicts.append(score_sim(sim, cfg.rubric))

    sev_counts = Counter((v.severity.value if v.severity else "pass") for v in verdicts)
    n = len(verdicts) or 1
    print("  severity distribution:")
    for sev in ("critical", "high", "medium", "low", "pass"):
        c = sev_counts.get(sev, 0)
        print(f"    {sev:9s} {c:5d}  ({round(100 * c / n)}%)")

    clusters = cluster_findings(verdicts)
    summary = dict(json.loads(run.get("config") or "{}"))
    summary["reprocessed_from_run"] = run["id"]
    new_id = Store(cfg.output.db_path).save_run("live", run.get("target", ""), verdicts, clusters, summary)
    print(f"  → saved new run {new_id}")
    if args.publish:
        import subprocess
        subprocess.run([sys.executable, str(ROOT / "scripts" / "publish.py")])
    return 0


if __name__ == "__main__":
    sys.exit(main())
