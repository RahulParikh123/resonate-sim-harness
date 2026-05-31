# Running the harness yourself — a cofounder's guide

You can run your own simulations, with your own settings, billed to your own
accounts. Mostly no code. Here's the whole thing end to end.

> **Billing, in one line:** the harness uses *your* API keys, so every run is
> charged to *your* provider accounts — never anyone else's. Set a spend cap on
> each provider (you can't be charged above it) and you're safe.

> **What it does:** the Resonate platform always drafts with **Grok**. A council of
> **five models — Claude, GPT, Gemini, Grok, Kimi** — then *reviews* each draft from
> five points of view (target voter, swing voter, opposition reader, quality coach,
> compliance). The five jobs **rotate across the five models every simulation**, so
> over a run every model plays every role — true, bias-balanced diversity. Reviewers
> score 0–100 and suggest improvements; **they never rewrite.**

---

## One-time setup (~10 minutes)

1. **Run the setup script** from the `resonate-sim-harness` folder:
   ```
   bash setup.sh
   ```
   It builds the Python environment, creates your keys file, and starts the local
   Resonate backend (if the repo is at `~/resonate-staging`).
2. **Get API keys + set a spend cap** on each provider (see `KEYS_SETUP.md`). For the
   full five-model council you want all five: **Anthropic, OpenAI, Google (Gemini),
   xAI, Moonshot (Kimi)**. Grok (xAI) does the drafting *and* a review slot, so give
   xAI the most headroom.
3. **Paste your keys into two files** (never in chat or Slack):
   - `resonate-sim-harness/.env` — all five council/reviewer keys
   - `~/resonate-staging/.env.local` — `XAI_API_KEY` (and optionally `ANTHROPIC_API_KEY`) for drafting
4. **Verify everything is connected** — one command, one tiny call per model, no keys printed:
   ```
   ~/resonate-harness-venv/bin/python scripts/check_models.py
   ```
   You want **5/5 connected**. If one fails it'll tell you why (usually a typo'd key,
   or a model ID that a provider has since renamed).

## Pick how the run is configured

Pick a ready-made preset, or edit one in the dashboard's **Configure** page (no files):

| Preset | What it does |
|---|---|
| `rotation-smoke` | Tiny, cheap check of the full 5×5 rotation (~15 sims). Run this first. |
| `quick-smoke` | Fast email + SMS sanity check. |
| `full-sweep` | Every channel & request type, fixed roster, up to 200. |
| `thousands` | The big one — full rotating council, ~1,200 simulations, stops at your caps. |

**Budgets** live in the preset (or the Configure page): `per_model_usd` caps **each
reviewing model** (default $10) and `backend_draft_usd` caps **Grok drafting**
(default $20). They're separate, hard ceilings — the run stops itself at the cap.
A full `thousands` run uses roughly **$12 Grok drafting + ~$10 Grok review**, so keep
about **$25+ of xAI credit** on hand.

## Run it

```
~/resonate-harness-venv/bin/python scripts/run_live.py --config configs/thousands.toml --council --preflight --review
```

- `--council`   = the five models generate varied, realistic campaign requests
- `--preflight` = let the platform ask its clarifying questions first
- `--review`    = run the rotating review council (the scores + suggestions)
- swap `thousands` for any preset above (start with `rotation-smoke`)

It drafts, caches the drafts to `runs/`, then reviews — and stops automatically at the
first budget cap. (If a run ever crashes mid-review, the drafts are already cached, so
you don't pay to redraft.)

## See the results

```
~/resonate-harness-venv/bin/streamlit run dashboard/app.py     # opens http://localhost:8501
```

Read the **About** page (loads first), then **Results**: average quality, what went
wrong ranked by importance, **By job** and **By model** breakdowns (the rotation), the
cost panel (per-model spend vs caps), every message with its surface, and a **How to
improve** digest. **Configure** edits criteria; **Trends** tracks quality across runs.

## Share a live link (optional)

To let someone view your dashboard without installing anything, open a tunnel to it
(one-time install: `brew install cloudflared`):

```
cloudflared tunnel --url http://localhost:8501
```

It prints a public `https://….trycloudflare.com` link that mirrors your dashboard
**live** — refresh shows the latest run. Caveats: it only works while your Mac and
this command are running, and the URL changes each time you restart it. (For an
always-on link you'd deploy to Streamlit Community Cloud — ask if you want that.)

## Reminder

The harness only **reviews** — it never rewrites your drafts or changes Resonate's
backend. Take its suggestions and apply fixes on your side.
