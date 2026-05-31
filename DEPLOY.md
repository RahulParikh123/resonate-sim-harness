# Put the dashboard on a durable, shareable link

**Why not Vercel?** Vercel only runs JavaScript / serverless functions — it can't host
a long-running Python **Streamlit** app like this dashboard. The free, always-on,
shareable equivalent is **Streamlit Community Cloud**, which gives you a stable
`https://<your-app>.streamlit.app` URL you can send to cofounders. This repo is already
set up for it (`requirements.txt`, and the dashboard reads `dashboard/published.db` when
hosted).

> The hosted dashboard is **read-only results** — it shows runs, it doesn't run them.
> Sims need the local Resonate backend + your keys, so each person runs locally
> (see `COFOUNDERS.md`) and *publishes* results to the shared link.

## Deploy it once (~3 minutes — only you can do this part)

1. Go to **https://share.streamlit.io** and **Sign in with GitHub** (authorize it).
2. Click **Create app → Deploy a public app from GitHub**.
3. Fill in:
   - **Repository:** `RahulParikh123/resonate-sim-harness`
   - **Branch:** `main`
   - **Main file path:** `dashboard/app.py`
4. (Optional) **Advanced settings → Python version: 3.11** or newer.
5. Click **Deploy**. In ~2 minutes you'll have your link: `https://<name>.streamlit.app`.

That URL is durable — it survives reboots and is safe to share. (Want it private?
In the app's **Settings → Sharing**, switch to "Only specific people" and add your
cofounders' emails.)

## Keep the link updated (it refreshes on every publish)

After any run, push the latest results to the live link:

```
~/resonate-harness-venv/bin/python scripts/publish.py
```

…or just add `--publish` to a run and it happens automatically:

```
~/resonate-harness-venv/bin/python scripts/run_live.py --config configs/thousands.toml --council --preflight --review --publish
```

Either way it copies your results into `dashboard/published.db`, commits, and pushes;
Streamlit Cloud redeploys automatically, so the public link shows the new run within
~1–2 minutes.

## Instant link (no deploy) — for a quick demo

If you just need to show someone right now without deploying, tunnel your local
dashboard (one-time `brew install cloudflared`):

```
cloudflared tunnel --url http://localhost:8501
```

It prints a live `https://….trycloudflare.com` URL — but only works while your Mac and
that command are running, and the URL changes each restart. Use Streamlit Cloud for the
durable link.
