#!/usr/bin/env python3
"""Live loop — request → (clarifying questions) → Grok draft → review council → flag → store.

    <venv>/bin/python scripts/run_live.py --config configs/example.harness.toml [--council] [--preflight] [--review]

Modes (compose freely):
  (default)    fixture requests → Grok drafts → objective rule checks       (needs a BACKEND key)
  --council    models generate varied campaign requests                     (needs council keys)
  --preflight  run the platform's clarifying-question flow before drafting  (needs keys) and record the Q&A
  --review     the review council reads each draft against its POV          (needs reviewer keys)

The platform always drafts with Grok; reviewers only review, never rewrite.
Safety: drives only generation endpoints. Never calls microtargeting /send.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Load the harness's own .env (your council/reviewer API keys) so LiteLLM picks them up.
try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:
    pass

from harness import council as council_mod  # noqa: E402
from harness.api_client import ApiError, ResonateClient  # noqa: E402
from harness.config import load_config  # noqa: E402
from harness.flagging import cluster_findings  # noqa: E402
from harness.labels import humanize_channel  # noqa: E402
from harness.llm import Budget, BudgetExceeded  # noqa: E402
from harness.report import print_breakdowns, print_clusters, print_legend  # noqa: E402
from harness.reviewers import aggregate_quality, review_draft, reviews_to_findings  # noqa: E402
from harness.runner import score_sim  # noqa: E402
from harness.schemas import SimResult  # noqa: E402
from harness.spend import backend_spend  # noqa: E402
from harness.store import Store  # noqa: E402


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--briefs", default=str(ROOT / "fixtures" / "sample_briefs.json"))
    ap.add_argument("--council", action="store_true", help="generate varied campaign requests with models (needs keys)")
    ap.add_argument("--preflight", action="store_true", help="run the platform's clarifying-question flow + record Q&A")
    ap.add_argument("--review", action="store_true", help="run the review council over each Grok draft (needs keys)")
    args = ap.parse_args()

    cfg = load_config(args.config)
    budget = Budget(cap_usd=cfg.budgets.council_usd)
    client = ResonateClient(base_url=cfg.target.base_url, dev_email=cfg.target.dev_email,
                            bearer_token=cfg.target.bearer_token or "")
    answerer = cfg.council.models[0] if cfg.council.models else "council/claude"

    print(f"\n  LIVE LOOP · {cfg.name} → {cfg.target.base_url}  (drafts by Grok)")
    print(f"  inputs={'model-generated' if args.council else 'fixtures'} · preflight={'on' if args.preflight else 'off'}"
          f" · review={'on' if args.review else 'off'} · {len(cfg.reviewers)} reviewers · cap ${cfg.budgets.council_usd:.0f}")
    print("  " + "─" * 64)
    await client.health()
    org_id, project_id = await client.bootstrap()
    print(f"  bootstrap ok · org={org_id[:8]}… project={project_id[:8]}…")

    # 1. requests
    if args.council:
        print("  generating campaign requests via council…")
        briefs = await council_mod.generate_matrix(cfg, budget=budget)
        if not briefs:
            print("  ⚠️  council produced nothing (need council keys?). Falling back to fixture requests.")
            briefs = json.loads(Path(args.briefs).read_text())
    else:
        briefs = json.loads(Path(args.briefs).read_text())
    briefs = briefs[: cfg.matrix.max_sims]
    print(f"  driving {len(briefs)} requests" + (" (with clarifying questions)" if args.preflight else "") + "…")

    # 2. (optional preflight) → Grok draft
    sem = asyncio.Semaphore(8)

    async def draft(i: int, b: dict):
        async with sem:
            ch, intent = b["channel"], b["intent"]
            itype, model, persona = b.get("intent_type", "fresh_draft"), b.get("model", ""), b.get("persona", "")
            surface = f"Uniform Messaging · {humanize_channel(ch)}"
            preflight_qa, draft_intent = list(b.get("preflight_qa") or []), intent
            if args.preflight:
                try:
                    pf = await client.preflight(project_id, intent, ch)
                    questions = [q.get("question", "") for q in (pf.get("questions") or [])][:6]
                    preflight_qa = await council_mod.answer_preflight(answerer, persona, intent, questions, budget)
                except (ApiError, Exception):
                    pass
            if preflight_qa:
                draft_intent = intent + "\n\nOperator clarifications:\n" + "\n".join(
                    f"- {x['q']} → {x['a']}" for x in preflight_qa)
            try:
                resp = await client.draft_batch(project_id, ch, draft_intent, output_family=b.get("output_family"),
                                                voice_mode=b.get("voice_mode", "light"))
                return ResonateClient.to_sim_result(f"sim-{i}", ch, itype, intent, b.get("brief_context", ""),
                                                    resp, model=model, persona=persona, surface=surface,
                                                    preflight_qa=preflight_qa), None
            except ApiError as e:
                return SimResult(id=f"sim-{i}", channel=ch, intent_type=itype, model=model, persona=persona,
                                 surface=surface, preflight_qa=preflight_qa, content_text="", brief_intent=intent,
                                 refused=True, produced_composer_draft=False), f"[{e.status}] {e.body[:120]}"

    drafted = await asyncio.gather(*[draft(i, b) for i, b in enumerate(briefs)])

    # 3. objective rule checks (deterministic + platform)
    verdicts = [score_sim(sim, cfg.rubric) for sim, _ in drafted]

    # 4. the review council — each reviewer scores the draft from its point of view
    if args.review and cfg.reviewers:
        print(f"  {len(cfg.reviewers)} reviewers scoring each draft from their point of view…")
        rsem = asyncio.Semaphore(4)

        async def review(idx: int):
            async with rsem:
                sim, _ = drafted[idx]
                try:
                    revs = await review_draft(sim, cfg.reviewers, budget=budget)
                    verdicts[idx].reviews = revs
                    verdicts[idx].quality_score = aggregate_quality(revs)
                    verdicts[idx].findings.extend(reviews_to_findings(revs))
                except BudgetExceeded as e:
                    print(f"  ⚠️  {e}")

        await asyncio.gather(*[review(i) for i in range(len(drafted))])

    # 5. cost, flag, store, report
    errors = [(s.id, err) for s, err in drafted if err]
    clusters = cluster_findings(verdicts)
    bspend = backend_spend(project_id) or {"total_usd": 0.0, "by_service": {}}
    council_usd, backend_usd = round(budget.spent_usd, 4), bspend["total_usd"]
    summary = {
        "config": cfg.name,
        "council_spent_usd": council_usd,        # reviewers + input generation (LiteLLM)
        "backend_spent_usd": backend_usd,        # Grok drafting (Resonate's spend_events)
        "total_usd": round(council_usd + backend_usd, 4),
        "backend_by_service": bspend["by_service"],
        "council_cap_usd": cfg.budgets.council_usd,
        "backend_cap_usd": cfg.budgets.backend_draft_usd,
    }
    Store(cfg.output.db_path).save_run("live", cfg.target.base_url, verdicts, clusters, summary)

    flagged = sum(1 for v in verdicts if not v.passed)
    scored = [v.quality_score for v in verdicts if v.quality_score is not None]
    avg_q = f"{round(sum(scored) / len(scored))}/100" if scored else "n/a"
    print(f"\n  RUN · {len(verdicts)} messages · {flagged} flagged · avg quality {avg_q}")
    print(f"  COST · total ${summary['total_usd']:.4f}  (reviewers ${council_usd:.4f} + Grok drafting "
          f"${backend_usd:.4f}) · saved → {cfg.output.db_path}\n")
    if errors:
        print(f"  ⚠️  {len(errors)} generation error(s) — e.g. {errors[0][1]}")
        print("      (503 → add a backend LLM key to ~/resonate-staging/.env.local)\n")
    print_clusters(clusters)
    print_breakdowns(verdicts)
    print_legend()
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
