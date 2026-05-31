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
import dataclasses
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Load the harness's own .env (your council/reviewer API keys) so LiteLLM picks them up.
# override=True is deliberate: a stale/empty API-key var exported in the shell would
# otherwise shadow the real key in .env and cause silent auth failures.
try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=True)
except Exception:
    pass

from harness import council as council_mod  # noqa: E402
from harness.api_client import ApiError, ResonateClient  # noqa: E402
from harness.config import load_config, rotate_reviewers  # noqa: E402
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
    ap.add_argument("--publish", action="store_true", help="after the run, push results to the hosted dashboard link")
    args = ap.parse_args()

    cfg = load_config(args.config)
    budget = Budget(per_model_cap=cfg.budgets.per_model_usd)
    client = ResonateClient(base_url=cfg.target.base_url, dev_email=cfg.target.dev_email,
                            bearer_token=cfg.target.bearer_token or "")
    models = cfg.council.models or ["claude", "gpt", "gemini", "grok", "kimi"]
    answerer = models[0]

    print(f"\n  LIVE LOOP · {cfg.name} → {cfg.target.base_url}  (drafts by Grok)")
    print(f"  inputs={'model-generated' if args.council else 'fixtures'} · preflight={'on' if args.preflight else 'off'}"
          f" · review={'on' if args.review else 'off'} · {len(cfg.jobs)} jobs × {len(models)} models rotating · "
          f"caps ${cfg.budgets.per_model_usd:.0f}/reviewing-model + Grok drafting ${cfg.budgets.backend_draft_usd:.0f}")
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
    briefs = briefs[: cfg.matrix.draft_cap]
    print(f"  driving {len(briefs)} requests" + (" (with clarifying questions)" if args.preflight else "") + "…")

    # 2. (optional preflight) → Grok draft
    sem = asyncio.Semaphore(8)

    async def draft(i: int, b: dict):
        async with sem:
            ch, intent = b["channel"], b["intent"]
            itype, model, persona = b.get("intent_type", "fresh_draft"), b.get("model", ""), b.get("persona", "")
            seg = b.get("target_segment", "")
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
                                                    preflight_qa=preflight_qa, target_segment=seg), None
            except ApiError as e:
                return SimResult(id=f"sim-{i}", channel=ch, intent_type=itype, model=model, persona=persona,
                                 surface=surface, target_segment=seg, preflight_qa=preflight_qa, content_text="",
                                 brief_intent=intent, refused=True, produced_composer_draft=False), f"[{e.status}] {e.body[:120]}"

    # Draft in chunks so the Grok cap can stop the run between chunks.
    indexed = list(enumerate(briefs))
    drafted: list = []
    CHUNK = 20
    for start in range(0, len(indexed), CHUNK):
        drafted += await asyncio.gather(*[draft(i, b) for i, b in indexed[start:start + CHUNK]])
        grok_spent = (backend_spend(project_id) or {}).get("total_usd", 0.0)
        if grok_spent >= cfg.budgets.backend_draft_usd:
            print(f"  ⚠️  Grok drafting hit its ${cfg.budgets.backend_draft_usd:.0f} cap (${grok_spent:.2f}) — "
                  f"stopping after {len(drafted)} of {len(briefs)} messages.")
            break

    # Cache successful drafts to disk BEFORE the (paid) review phase, so a crash or a
    # later criteria change can re-score the same drafts without paying to re-draft.
    try:
        cache_path = ROOT / "runs" / f"drafts-{cfg.name}.json"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        ok_cache = [dataclasses.asdict(s) for s, e in drafted if not e and (s.content_text or "").strip()]
        cache_path.write_text(json.dumps(ok_cache))
        print(f"  cached {len(ok_cache)} drafts → runs/{cache_path.name} (safe from crashes / reusable)")
    except Exception:
        pass

    # 3. expand drafts → simulations under the ROTATING council, score each.
    ok_drafts = [sim for sim, err in drafted if not err and (sim.content_text or "").strip()]
    jobs = cfg.jobs

    if not (args.review and jobs and models):
        # No review council requested: one verdict per draft (deterministic + platform checks only).
        verdicts = [score_sim(sim, cfg.rubric) for sim, _ in drafted]
    else:
        # Build simulation units rotation-major for even coverage: at rotation r, draft d
        # gets model↔job offset (d + r) % len(models), so across r=0..N-1 every model plays
        # every job. Capped at max_sims; the loop stops once a reviewing model hits its cap.
        R = max(1, cfg.matrix.rotations_per_draft)
        units = []  # (draft_sim, offset, rotation_index)
        for r in range(R):
            for d, sim in enumerate(ok_drafts):
                if len(units) >= cfg.matrix.max_sims:
                    break
                units.append((sim, (d + r) % len(models), r))
            if len(units) >= cfg.matrix.max_sims:
                break
        print(f"  reviewing {len(ok_drafts)} drafts · {len(jobs)} jobs × {len(models)} models rotating "
              f"→ {len(units)} simulations…")

        stop = {"capped": False}
        rsem = asyncio.Semaphore(5)

        def capped_model():
            return next((m for m in models if budget.spent_by_model.get(m, 0.0) >= budget.cap_for(m)), None)

        async def simulate(draft_sim: SimResult, offset: int, r: int):
            if stop["capped"]:
                return None
            async with rsem:
                if stop["capped"]:
                    return None
                try:
                    sim = dataclasses.replace(draft_sim, id=f"{draft_sim.id}-r{r}")
                    v = score_sim(sim, cfg.rubric)
                    revs = await review_draft(sim, rotate_reviewers(jobs, models, offset), budget=budget)
                    v.reviews = revs
                    v.quality_score = aggregate_quality(revs)
                    v.findings.extend(reviews_to_findings(revs))
                except Exception as e:  # one bad sim must never sink the whole run
                    print(f"  ⚠️  sim {draft_sim.id} r{r} failed ({type(e).__name__}: {str(e)[:70]}) — skipped.")
                    return None
                m = capped_model()
                if m and not stop["capped"]:
                    stop["capped"] = True
                    print(f"  ⚠️  reviewing model '{m}' hit its ${budget.cap_for(m):.0f} cap — stopping the rotation.")
                return v

        results = await asyncio.gather(*[simulate(s, o, r) for s, o, r in units], return_exceptions=True)
        verdicts = [v for v in results if v is not None and not isinstance(v, BaseException)]
        # Keep deterministic verdicts for drafts that errored/refused (so they still surface).
        verdicts += [score_sim(sim, cfg.rubric) for sim, err in drafted
                     if err or not (sim.content_text or "").strip()]

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
        "council_by_model": {m: round(c, 4) for m, c in budget.spent_by_model.items()},
        "council_cap_usd": cfg.budgets.council_usd,
        "per_model_cap_usd": cfg.budgets.per_model_usd,
        "backend_cap_usd": cfg.budgets.backend_draft_usd,
        "drafts": len(ok_drafts),
        "simulations": len(verdicts),
    }
    Store(cfg.output.db_path).save_run("live", cfg.target.base_url, verdicts, clusters, summary)

    flagged = sum(1 for v in verdicts if not v.passed)
    scored = [v.quality_score for v in verdicts if v.quality_score is not None]
    avg_q = f"{round(sum(scored) / len(scored))}/100" if scored else "n/a"
    print(f"\n  RUN · {len(verdicts)} simulations over {len(ok_drafts)} Grok drafts · {flagged} flagged · "
          f"avg quality {avg_q}")
    print(f"  COST · total ${summary['total_usd']:.4f}  (reviewers ${council_usd:.4f} + Grok drafting "
          f"${backend_usd:.4f}) · saved → {cfg.output.db_path}")
    if summary["council_by_model"]:
        per = "  ".join(f"{m} ${c:.2f}" for m, c in sorted(summary["council_by_model"].items()))
        print(f"  per reviewing model (cap ${cfg.budgets.per_model_usd:.0f} each): {per}")
    print()
    if errors:
        print(f"  ⚠️  {len(errors)} generation error(s) — e.g. {errors[0][1]}")
        print("      (503 → add a backend LLM key to ~/resonate-staging/.env.local)\n")
    print_clusters(clusters)
    print_breakdowns(verdicts)
    print_legend()
    print()
    if args.publish:
        import subprocess
        print("  publishing results to the hosted dashboard link…")
        subprocess.run([sys.executable, str(ROOT / "scripts" / "publish.py")])
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
