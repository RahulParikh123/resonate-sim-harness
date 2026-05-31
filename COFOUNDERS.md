# Running the harness yourself — a cofounder's guide

You can run your own simulations, with your own settings, billed to your own
accounts. No code. Here's the whole thing.

> **Billing, in one line:** the harness uses *your* API keys, so every run is
> charged to *your* provider accounts — never anyone else's. Set a spend cap on
> each provider (you can't be charged above it) and you're safe.

---

## One-time setup (about 10 minutes)

1. **Run the setup script** from the `resonate-sim-harness` folder:
   ```
   bash setup.sh
   ```
   It builds the Python environment, creates your keys file, and starts the local
   backend (if the Resonate repo is at `~/resonate-staging`).
2. **Get API keys + set a spend cap** on each provider. See `KEYS_SETUP.md` for the
   click-by-click. You need at least one of Anthropic or xAI (for drafting); add
   OpenAI / Gemini for more diverse reviewers.
3. **Paste your keys into two files** (never in chat or Slack):
   - `resonate-sim-harness/.env` — your council/reviewer keys
   - `~/resonate-staging/.env.local` — `XAI_API_KEY` and/or `ANTHROPIC_API_KEY` (drafting)
   Save them. The keys stay on your machine, so every run is billed to you.

## Pick how the run is configured

Either **pick a ready-made preset** or **edit one in the dashboard** (no files):

| Preset | What it does |
|---|---|
| `quick-smoke` | Fast sanity check — email + SMS, ~8 messages. Start here. |
| `example.harness` | Balanced default — email + SMS, the full review council. |
| `full-sweep` | Comprehensive — every channel & request type, up to 200 messages. |

To make your own: open the **Configure** page in the dashboard, edit the reviewers
(who they proxy + their standards), the channels, and the budgets, then **Save** —
it writes a new preset you can run.

## Run it

```
~/resonate-harness-venv/bin/python scripts/run_live.py --config configs/quick-smoke.toml --preflight --review
```

- `--preflight` = let the platform ask its clarifying questions first (recommended)
- `--review`    = run the review council (the scores + suggestions)
- swap `quick-smoke` for `example.harness` or `full-sweep` (or your own saved preset)

It stops automatically when it hits your budget cap.

## See the results

```
~/resonate-harness-venv/bin/streamlit run dashboard/app.py     # opens http://localhost:8501
```

Read the **About** page (it loads first), then the **Results** page: the average
quality score, what went wrong ranked by importance, the per-reviewer scores, every
message with which surface it came from, and a **How to improve** digest. Use
**Configure** to change criteria and **Trends** to watch quality climb across runs.

## Reminder

The harness only **reviews** — it never rewrites your drafts or changes Resonate's
backend. Take its suggestions and apply fixes on your side.
