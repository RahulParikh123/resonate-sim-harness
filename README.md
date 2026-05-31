# Resonate Simulation Harness

A **council-of-models QA harness** that drives the **Resonate** campaign-messaging
platform like thousands of operators would, has a panel of independent models
review every message Grok drafts, and surfaces only the *patterns* worth your
attention — so you catch bad output **before** the platform touches a real campaign.

> Status: **live**. All five models are connected and verified, the rotating
> review council runs end-to-end against a local Resonate backend, and a run of
> ~1,200 simulations fits inside the budget caps below.

---

## The five-model council and their jobs

The platform **always drafts with Grok** — the harness never changes that. The
council is a panel of **reviewers** that read each Grok draft and score it. They
**review and suggest; they never rewrite.**

**Five models — one per provider** (the diversity backbone):

| Model | Provider | Model ID used here | Flagship available |
|---|---|---|---|
| Claude | Anthropic | `claude-haiku-4-5` | `claude-opus-4-1`, `claude-sonnet-4-5` |
| GPT | OpenAI | `gpt-4o-mini` | `gpt-4o`, `gpt-5*` |
| Gemini | Google | `gemini-2.5-flash` | `gemini-2.5-pro` |
| Grok | xAI | `grok-3` | `grok-4` |
| Kimi | Moonshot | `moonshot-v1-8k` | — |

We run the **fast/cheap** variant of each so thousands of reviews fit the budget.
Swap in the flagships (in `harness/llm.py`) for a smaller, sharper run.

**Five jobs — the points of view each message is judged from:**

1. **Target-segment voter** — the group the message is tailored to. Does it actually land for us, or is it a generic pander?
2. **Skeptical swing voter** — undecided, distrustful. Does it move me, or read as spin?
3. **Hostile / opposition reader** — an opponent hunting for ammunition. What could backfire or be clipped out of context?
4. **Message-quality coach** — a copy chief. Is this the *best* version? Clarity, hook, single ask, length-fit.
5. **Compliance & legal guardrail** — a campaign lawyer. Missing "Paid for by", unverified claims, FEC/FCC/TCPA exposure.

### Jobs rotate across models every run — for true diversity

Each simulation assigns the five jobs to the five models, and **the assignment
rotates every simulation** (a Latin square):

```
              Target   Swing    Opposition  Coach    Compliance
sim #1 (off 0) Claude   GPT      Gemini      Grok     Kimi
sim #2 (off 1) GPT      Gemini   Grok        Kimi     Claude
sim #3 (off 2) Gemini   Grok     Kimi        Claude   GPT
sim #4 (off 3) Grok     Kimi     Claude      GPT      Gemini
sim #5 (off 4) Kimi     Claude   GPT         Gemini   Grok
```

Over a full cycle **every model plays every job exactly once**, so no single
model's bias colours any single point of view. Each reviewer returns a **0–100
score**, an optional **concern**, and one concrete **"how to improve"** — reward,
not just punishment. Set `rotations_per_draft` to re-review each draft under
several rotations and multiply drafts into thousands of simulations.

---

## Budget: two separate ledgers

| Cap | Default | What it limits |
|---|---|---|
| `per_model_usd` | **$10** | a hard cap on **each reviewing model** (Claude, GPT, Gemini, Grok, Kimi) |
| `backend_draft_usd` | **$20** | a hard cap on **Grok drafting** (the platform's language agent) |

Grok appears in two places — it **drafts every message** (backend, the $20 cap)
**and** takes a reviewer slot in the rotation (its own $10 cap). These are
**separate ledgers**: Grok-as-reviewer never eats the drafting budget, and vice versa.

**How thousands of simulations fit the budget:** drafting is the only pricey
step (~$0.02–0.05 per Grok draft), so $20 buys ~400–800 distinct drafts. The
review council is cheap (Grok-3 is the priciest reviewer at ~$0.008/review), and
re-reviewing drafts under rotations multiplies them into **~1,200 simulations**
before Grok-as-reviewer hits its $10 cap — the binding limit. Raise the caps to
go higher. The run **stops itself** the moment either cap is reached.

> xAI note: Grok is used for *both* drafting and a reviewer slot, so a full run
> can spend up to ~$30 on xAI ($20 + $10). Keep enough xAI credit on hand.

---

## Quick start

```bash
VENV=~/resonate-harness-venv         # lives outside this folder so it doesn't sync to OneDrive

# 0. Confirm all five models are connected (one tiny live call each; never prints keys)
$VENV/bin/python scripts/check_models.py

# 1. Tiny sanity check of the rotation (a few drafts, full 5×5 council)
$VENV/bin/python scripts/run_live.py --config configs/rotation-smoke.toml --council --preflight --review

# 2. The real thing — thousands of simulations, stops at your budget caps
$VENV/bin/python scripts/run_live.py --config configs/thousands.toml --council --preflight --review

# 3. Read the results (opens http://localhost:8501)
$VENV/bin/streamlit run dashboard/app.py
```

**Modes** (compose freely): `--council` (models generate varied campaign
requests), `--preflight` (run the platform's clarifying-question flow and record
the Q&A so reviewers can judge it), `--review` (run the rotating review council).
Without `--review` you get the instant objective checks only.

**Keys** live only in `.env` (this folder, git-ignored) for the council/reviewers
and in `~/resonate-staging/.env.local` for Grok drafting — never in chat, never
committed. See **KEYS_SETUP.md**. If a model fails `check_models.py`, it's almost
always a stale model ID or a shell variable shadowing `.env` (the loaders use
`override=True` to prevent the latter).

## Configs (the human gates)

Every gate lives in an editable **TOML** file, or use the dashboard's **Configure**
page (no file editing):

| Preset | What it's for |
|---|---|
| `configs/rotation-smoke.toml` | tiny, cheap rotation sanity check (~15 sims) |
| `configs/thousands.toml` | full rotating council at scale, ~1,200 sims, stops at caps |
| `configs/full-sweep.toml` | every channel × request type, fixed roster |
| `configs/quick-smoke.toml` | fast email+SMS check |
| `configs/example.harness.toml` | the commented template — copy & edit per campaign |

```bash
cp configs/thousands.toml configs/my-campaign.toml   # …edit jobs, models, caps, matrix…
$VENV/bin/python scripts/run_live.py --config configs/my-campaign.toml --council --preflight --review
```

---

## How scoring works

Each Grok draft is scored in three layers, cheapest first:

1. **Deterministic** (pure stdlib, instant): leftover template placeholders,
   fabricated URLs/phones, wrong length for the channel, missing/soft
   "Paid for by", raw markdown in plain-text channels, empty/refused drafts,
   feedback-in-chat that wrongly changed the draft.
2. **Platform-native signals**: what Resonate already returns
   (`stance_drift_score`, `advisory_flags`, `refused`).
3. **The rotating review council**: the five models scoring 0–100 from their
   rotated points of view, plus a "how to improve" suggestion.

Flagging is **cluster-first**: problems are grouped so you review ~30 patterns,
not thousands of rows. Everything is plain-English in the dashboard — no internal
codenames (`harness/labels.py` maps every internal key to a human label).

---

## Safety posture (non-negotiable)

- **No real sends.** Runs require `INTEGRATIONS_LIVE_DISPATCH_OK=false` (default);
  the backend downgrades every "live" vendor to "shadow" and mock adapters refuse
  to send. Even "submit" cannot dispatch.
- **Hard budget ceilings** with kill-switches on every reviewing model and on
  Grok drafting; the run stops itself at the cap.
- **Isolated data**: a throwaway org+project on a non-prod backend; a prod
  hostname is refused unless a real bearer token is explicitly supplied.
- **Reviewers never rewrite.** They flag and suggest; your team applies fixes.

---

## Layout

```
resonate-sim-harness/
├── harness/
│   ├── llm.py          # LiteLLM wrapper, MODEL_MAP (verified IDs), COUNCIL_MODELS, per-model Budget
│   ├── config.py       # TOML model + loader; Job, DEFAULT_JOBS, rotate_reviewers()
│   ├── reviewers.py    # the review council — score 0–100 + concern + how-to-improve
│   ├── council.py      # generate varied operator requests + answer preflight questions
│   ├── api_client.py   # live Resonate backend driver (drafts via /language/draft-batch)
│   ├── spend.py        # Grok drafting cost from the backend (docker-exec fallback)
│   ├── runner.py · flagging.py · store.py · schemas.py · labels.py · report.py
│   └── scorers/        # deterministic.py · platform.py
├── scripts/
│   ├── check_models.py # confirm all 5 providers connect ✅
│   ├── run_live.py     # the live loop: request → Grok draft → rotating review → flag → store
│   └── run.py · demo_scorer.py · run_dryrun.py   # keyless demos
├── configs/            # rotation-smoke · thousands · full-sweep · quick-smoke · example
├── dashboard/app.py    # Streamlit: About gate · Results · Configure · Trends · cost panel
└── tests/              # 26 tests (config, rotation Latin-square, budget, scoring) ✅
```
