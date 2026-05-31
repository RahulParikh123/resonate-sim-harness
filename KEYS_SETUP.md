# Getting your API keys — a 10-minute, non-technical guide

You don't touch any code. You create accounts at the AI providers, generate
"API keys," and set a spending cap on each. (An API key is like a password that
lets the harness use that provider's AI. The spending cap means you can never be
charged more than you choose.)

> Poozed Man can't do this part for you — every signup needs *your* email, *your*
> payment method, and *you* agreeing to each provider's terms. But below is every
> click. When you've pasted the keys, Poozed Man does the rest.

---

## ① You only need ONE key to start

To see the whole backend draft path generate real drafts, you need **just one**
of these: **Anthropic (Claude)** *or* **xAI (Grok)**. Add the others later for
the multi-model council + judges. Start with **Anthropic** if unsure.

## ② Always set a budget cap

On every provider, set a hard monthly spend limit (e.g. **$20**). This is your
real protection. The pattern at every provider is the same:

> **sign up → Billing (set a limit) → API Keys (create one) → copy it**

## ③ Where the key goes

The backend key lives in one file: **`~/resonate-staging/.env.local`**.
When you're ready, just tell Poozed Man — it'll open that file for you in
TextEdit. Paste the key after the matching `=`, then save. **Never paste keys
into the chat.**

---

## Provider-by-provider

### 1) Anthropic — Claude  *(recommended first — this is the draft model)*
1. Go to **console.anthropic.com**, sign up / log in.
2. **Billing** → add a payment method → set a **monthly spend limit** (e.g. $20).
3. **API Keys** → **Create Key** → copy it (begins with `sk-ant-`).
4. Paste into `.env.local` as → `ANTHROPIC_API_KEY=sk-ant-...`

### 2) xAI — Grok  *(works as the draft model too, and joins the council)*
1. **console.x.ai** → sign up.
2. **Billing / Credits** → add payment → set a spend limit.
3. **API Keys** → create → copy.
4. → `XAI_API_KEY=...`

### 3) OpenAI — GPT / Codex  *(council + judge — add later)*
1. **platform.openai.com** → sign up.
2. **Settings → Billing** → add payment → **Limits** → set a monthly cap.
3. **API keys** → **Create new secret key** → copy (`sk-...`).
4. → `OPENAI_API_KEY=...`

### 4) Google — Gemini  *(council + judge — add later)*
1. **aistudio.google.com** → **Get API key** → create.
2. Free tier exists; for paid, link a Google Cloud billing account and set a
   budget cap in Cloud Billing.
3. → `GEMINI_API_KEY=...`

### 5) Moonshot — Kimi  *(council — add later)*
1. **platform.moonshot.ai** → sign up.
2. **Billing** → load a credit amount (the amount you load *is* your cap).
3. **API Keys** → create → copy.
4. → `MOONSHOT_API_KEY=...`

> Provider menus get renamed over time — if a label looks different, the path is
> always sign-up → billing/limits → API keys.

---

## What each key unlocks

| Keys you add | What turns on |
|---|---|
| Anthropic **or** xAI | **Backend draft path** — the harness generates real drafts to test (start here) |
| + OpenAI, Gemini, Kimi | **Council** — diverse models writing realistic operator briefs |
| any 2–3 of the above | **Judge panel** — scoring quality (different AI labs = less bias) |

## Now vs. later (so you're not overwhelmed)

- **Right now:** put **one** backend key (`ANTHROPIC_API_KEY` or `XAI_API_KEY`)
  in `~/resonate-staging/.env.local`. That's it.
- **Later:** the council/judge keys go in a second file (`resonate-sim-harness/.env`)
  — Poozed Man will set that up with you when you add them.

## When you're done
1. Save the file.
2. Tell Poozed Man **which provider(s) you added**.
3. Poozed Man restarts the backend and runs the first real batch — you'll see
   flagged results in a couple of minutes.
