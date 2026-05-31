# How the simulation harness works — in plain English

This explains every layer of the system, no technical background needed.

---

## The big idea (one paragraph)

Resonate writes political-campaign messaging, and it always uses **Grok** to do
the writing. Before any of that reaches a real campaign, this platform feeds
Resonate thousands of realistic campaign requests, lets Grok draft each one, and
then hands every draft to a **council of reviewers** — different AI models, each
role-playing a critic with its own standards — to judge whether it's up to
scratch. The reviewers never rewrite anything; they only review. Then the bad
results are grouped into patterns and shown to you, worst and most-frequent first.

---

## Follow one simulation from start to finish

1. **A realistic request goes in.** "Write a GOTV email," "draft a 30-second TV
   spot," "give me a contrast line on my opponent's record" — across every channel.
2. **Grok drafts it.** Resonate's own engine (always Grok) writes the message,
   exactly as it would for a real customer. *We never change this.*
3. **Instant rule checks run (free).** Objective checks scan the draft: leftover
   placeholders, invented links, wrong length for the channel, missing "Paid for by."
4. **The review council weighs in.** Several *different* models, each playing a
   critic with its own standards, read the draft and return a verdict — meets,
   concern, or fail — with a one-line reason. They do **not** rewrite it.
5. **It gets filed.** Pass or fail, the result is saved with its channel, request
   type, and every reviewer's verdict.
6. **You see patterns.** Failures are grouped and ranked, with breakdowns by
   reviewer, channel, and request type.

---

## The layers, one by one

### 1. LiteLLM — the universal adapter (+ your money safety)
One universal adapter to every AI provider (Anthropic, OpenAI, Google, xAI,
Moonshot), and the place your **hard budget caps** live. Hit the ceiling and the
providers simply stop — you cannot be overcharged.

### 2. Campaign inputs — variety
A growing set of realistic requests a real campaign might type, across every
channel and request type (fresh draft, revision, chat-only discussion, edge case).
These can be model-generated for variety. They are just *inputs* — the personas
that matter live on the review side.

### 3. The platform — Grok drafts
Resonate's real backend generates each draft, and it always uses Grok. The harness
drives the real API and only ever asks it to *write*; it can never send a message
to a real voter.

### 4. The review council — the heart of it
A panel of different models, each role-playing a critic with its **own criteria**:
a compliance-and-legal hawk with low risk tolerance; a punchy persuader who rewards
bold copy and dislikes bland writing; a moderate who flags inflammatory or offensive
language; a guardian of the candidate's voice and positions. Each reviews the same
Grok draft against its own standard and never rewrites it. Because the standards
differ on purpose, a draft can pass one reviewer and fail another — **that split is
the signal**, telling you how a message holds up against different appetites for
tone and risk. Using diverse models makes the panel far harder to fool than any
single critic.

### 5. The objective checks
Alongside the reviewers, instant rule checks catch the black-and-white failures
(placeholders, fabricated links/numbers, length contracts, missing disclaimers),
plus signals Resonate itself returns (like a stance-drift score). These need no
opinion, so they run on every draft for free.

### 6. Flagging & ranking — so you're not buried
Every problem is grouped into a plain-English issue, ranked by **how serious × how
often**, so the biggest, most common problems float to the top. Reviewer verdicts
are grouped by reviewer, so you can see which critic objects most.

### 7. Storage & dashboard — where results live
Every run is saved (a single local file now; a shared database at scale), tagged by
channel, request type, and each reviewer's verdict. That's what powers the
breakdowns and the dashboard's filters, drill-downs, and trends.

---

## Where you configure the criteria

Everything lives in one editable place — either the `configs/*.toml` files or the
dashboard's point-and-click **Configure** page: the reviewers (their names, models,
and standards), the objective checks, the channel/request-type matrix, and the
budgets. Copy a config per campaign, commit it, re-run it — every run is
reproducible and self-documents its settings.

## How to make it more realistic & robust

- **Add or sharpen reviewers** — more critic standards = more angles covered.
- **Add channels and request types** — broader coverage of what campaigns ask for.
- **Raise the repeat count and cap** — more loops surface rarer failures.
- **Use diverse reviewer models** — different labs catch different things.

## How to read a run's output

- **What went wrong, most important first** — the failure patterns, worst first.
- **By reviewer** — which critic raised the most concerns.
- **By channel / by request type** — where the platform struggles.
- **Every simulated message** — open any one to see exactly what it got wrong.
