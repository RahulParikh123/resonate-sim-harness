# Resonate Simulation Harness

A council-of-models QA harness that drives the **Resonate** campaign-messaging
platform like thousands of operators would, scores every output, and surfaces
only the *patterns* worth your attention — so you can catch failures **before**
the platform touches a real campaign.

> Status: **MVP-zero** — the deterministic scorer is built and runnable today
> (no keys, no backend). The live driver + council + judge layers are next.

---

## How it works

A thin **asyncio** harness talks to Resonate's backend API directly (no browser),
authenticating with the dev-auth header against a **dedicated test/staging
backend**. A **council of diverse models** (Claude, GPT/Codex, Gemini, Kimi,
Grok — via **LiteLLM**) plays *simulated operators*, fanning briefs across
**personas × channels × intents**. Each captured output is scored in three
layers, cheapest first:

1. **Deterministic** (this MVP — pure stdlib, instant): scaffolding/placeholder
   leaks, fabricated URLs/phones, broadcast over-length, missing/soft
   "Paid for by", raw markdown in plain-text channels, empty/refused drafts,
   chat-routing violations.
2. **Platform-native signals**: the values Resonate already returns
   (`stance_drift_score`, `advisory_flags`, `refused`) + in-process FEC/TCPA/FCC
   validators.
3. **Diverse judge panel**: subjective axes only (on-message/stance fidelity,
   persuasiveness, voice, factual integrity). The model that *authored* a draft
   never judges it, and judge **disagreement** is itself a flag.

Flagging is **cluster-first**: failures are grouped so you review ~30 patterns,
not 10,000 rows.

### Per-surface test tracks
The platform is many surfaces, not one chat box — so the harness splits:
- **Generation** (council drives, judges score the prose): Uniform Messaging
  (7 channels incl. the Speeches/Docs · Radio · TV mediums), Assistant chat,
  Microtargeting (batch variants + sign-off — *dispatch-adjacent*).
- **Scoring/judgment** (feed known inputs, check the scores discriminate):
  Synthetic Focus Groups, Voter Atlas.
- **Data**: Deep Learning Survey (lower pre-deploy priority).

---

## Run it (zero setup)

```bash
python3 scripts/demo_scorer.py                          # deterministic scorer over sample drafts
python3 scripts/run.py --config configs/example.harness.toml   # full config-driven pipeline
```

Both run on the stdlib alone — no install, no API keys, no backend.

## Configure & re-run (for your cofounders)

Every human gate lives in a **TOML config** — the rubric, council roster, judge
panel, sim matrix, budgets, and target backend. To run your own simulation:

```bash
cp configs/example.harness.toml configs/my-campaign.toml
#   …edit it (toggle rubric dimensions, set thresholds, pick models, set budgets)…
python3 scripts/run.py --config configs/my-campaign.toml
```

Each config is one reproducible, shareable simulation. Commit it to git; anyone
on the team gets the exact same run. The config is echoed at the top of every
run, so results are self-documenting. (Prefer point-and-click? The dashboard's
**Configure** page edits and saves configs with no file editing.)

## Dashboard

```bash
<venv>/bin/streamlit run dashboard/app.py     # opens http://localhost:8501
```

Three views: **Results** (metrics, failure clusters, per-model / per-persona /
per-channel breakdowns, per-sim drill-down, judge-disagreement queue),
**Configure** (point-and-click criteria editor), and **Trends** (clean-rate and
flags across all runs).

## Live runs (needs keys)

```bash
<venv>/bin/python scripts/run_live.py --config configs/<name>.toml [--council] [--judge]
```

- default → fixture briefs → real drafts → instant scoring (needs a backend key)
- `--council` → council models generate the briefs (needs council keys)
- `--judge` → judge panel scores subjective axes on survivors (needs judge keys)

Keys: see **KEYS_SETUP.md**. The harness venv lives outside this folder at
`~/resonate-harness-venv` (so it doesn't sync to OneDrive).

---

## Safety posture (non-negotiable)

- **No real sends.** Runs require `INTEGRATIONS_LIVE_DISPATCH_OK=false` (default);
  the backend downgrades every "live" vendor to "shadow" and mock adapters refuse
  to send. No vendor secrets are supplied. Even "submit" cannot dispatch.
- **Two hard budget ceilings** with kill-switches: council/judge spend (LiteLLM)
  and Resonate's own draft spend (`spend_events`).
- **Isolated data**: a throwaway org+project on a non-prod backend; a prod
  hostname is refused unless a real bearer token is explicitly supplied.

---

## Layout

```
resonate-sim-harness/
├── harness/
│   ├── config.py               # TOML config model + loader ✅
│   ├── schemas.py              # SimResult, Finding, Severity ✅
│   ├── flagging.py             # severity tiers + clustering ✅
│   ├── store.py                # SQLite persistence ✅
│   ├── runner.py               # score → flag → store; dry-run + config-driven ✅
│   ├── scorers/
│   │   ├── deterministic.py    # Layer 1 — config-driven ✅
│   │   ├── platform.py         # Layer 2 — config-driven ✅
│   │   └── judge.py            # Layer 3 — scaffold (wires once keys land)
│   ├── api_client.py           # live backend driver — scaffold
│   └── council.py              # operator brief generator — scaffold
├── scripts/
│   ├── demo_scorer.py          # deterministic scorer demo ✅
│   ├── run_dryrun.py           # default-rubric pipeline ✅
│   └── run.py                  # config-driven pipeline ✅
├── configs/example.harness.toml  # the human gates — copy & edit per campaign ✅
├── fixtures/sample_drafts.json
├── tests/test_scorers.py       # 10 tests, all green ✅
├── litellm.config.yaml         # council + judge model map (roster TBD)
├── .env.example  ·  pyproject.toml
```

## What's needed to go live
1. A non-prod Resonate backend the harness can hit (staging deploy, or a local
   `docker compose` + `uv` equivalent) with dev-auth + mock dispatch.
2. Provider API keys in `.env` (council + judge).
3. Your sign-off on the rubric, council roster, sim volume, and budgets.
