"""Resonate Sim Harness — results + configuration dashboard.

    <venv>/bin/streamlit run dashboard/app.py

Three views (left sidebar):
  • Results   — review a run: metrics, cluster triage, per-model/persona/channel
                breakdowns, per-sim drill-down, judge-disagreement queue.
  • Configure — point-and-click editor for the criteria/config (no file editing).
  • Trends    — pass-rate and flags across all runs over time.
"""

from __future__ import annotations

import json
import os
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402
import tomli_w  # noqa: E402

from harness.labels import (  # noqa: E402
    describe, humanize_channel, humanize_intent, humanize_message_id, humanize_mode,
    humanize_model, humanize_severity, humanize_source, label,
)
from harness.store import Store  # noqa: E402

def _resolve_db() -> str:
    """Local runs use runs/harness.db. On the hosted (Streamlit Cloud) dashboard that
    file isn't in the repo, so fall back to the committed snapshot dashboard/published.db
    (refreshed by scripts/publish.py). HARNESS_DB overrides everything."""
    env = os.environ.get("HARNESS_DB")
    if env:
        return env
    live = ROOT / "runs" / "harness.db"
    return str(live if live.exists() else ROOT / "dashboard" / "published.db")


DB_PATH = _resolve_db()
CONFIG_DIR = ROOT / "configs"
SEV_EMOJI = {"critical": "⛔", "high": "🔴", "medium": "🟠", "low": "🟡", "pass": "✅"}

# (dimension, scored_by, default_severity)  — drives the Configure editor
DIMENSIONS = [
    ("scaffolding_leak", "deterministic", "high"),
    ("empty_or_refused", "deterministic", "high"),
    ("fabricated_operational_info", "deterministic", "high"),
    ("chat_routing", "deterministic", "high"),
    ("length_contract", "deterministic", "(default)"),
    ("markdown_in_plaintext", "deterministic", "medium"),
    ("compliance_phrasing", "deterministic", "medium"),
    ("stance_drift", "platform", "(default)"),
]
ALL_CHANNELS = ["email", "sms", "speech", "mail", "radio", "tv", "social"]
ALL_INTENTS = ["fresh_draft", "revision", "discussion", "edge_case"]
SEV_OPTS = ["(default)", "critical", "high", "medium", "low"]

st.set_page_config(page_title="Resonate · Sim Harness", layout="wide", page_icon="🧭")

ABOUT_HTML = """
<div style="max-width: 880px; font-size: 0.9rem; line-height: 1.6; color: #dcdcdc;">

  <div style="border-left: 3px solid #e8794a; background: rgba(232,121,74,0.08);
              padding: 14px 18px; margin: 4px 0 26px; border-radius: 5px;">
    <strong>In three sentences.</strong> This is a private quality-testing platform for Resonate. Before
    Resonate writes a single message for a real campaign, this tool runs thousands of simulated campaigns
    through it and automatically flags anything that falls short of standard. Everything on the next page is
    the organized result of that testing &mdash; sorted so you can see what to fix first in a couple of minutes.
  </div>

  <h3 style="font-size:1.05rem; margin:1.4em 0 .4em;">Why this exists</h3>
  <p>Resonate is an AI platform that writes political-campaign messaging &mdash; fundraising and persuasion
  emails, get-out-the-vote texts, stump speeches, direct mail, radio and television scripts, and social posts.
  Those words go to real voters, carry legal obligations, and shape how a candidate is perceived; once a
  message is sent, it cannot be unsent. That makes the quality of every draft genuinely high-stakes. The
  purpose of this platform is simple: pressure-test that quality in private, at scale, before any of it reaches
  a paying campaign. Think of it as a crash-test facility for campaign messaging &mdash; we deliberately try to
  make the system produce bad output here, in a sealed environment, so that it doesn&rsquo;t happen out there.</p>

  <h3 style="font-size:1.05rem; margin:1.4em 0 .4em;">How it was built &mdash; reading the whole system first</h3>
  <p>The agent that built this began by reading through Resonate&rsquo;s entire backend, end to end, rather
  than guessing at how it works. It mapped every place where the platform interacts with a customer and, more
  importantly, every place where it generates language from scratch. In Resonate, brand-new text is created in
  several distinct spots: the main drafting workspace where an operator writes a message in any channel, the
  microtargeting tool that mass-produces tailored variants for different voter segments, the assistant chat
  that can draft or revise on command, and the modeling tools that score messages against simulated voters.
  Knowing exactly where this &ldquo;net-new&rdquo; text is born matters, because those are precisely the
  moments worth testing &mdash; the points where the AI is inventing words a campaign might actually send. This
  platform drives those same pathways directly, the way the real product does.</p>

  <h3 style="font-size:1.05rem; margin:1.4em 0 .4em;">The core idea &mdash; Grok drafts, a council of reviewers judges</h3>
  <p>Two things happen for every test. First, the platform feeds Resonate a realistic campaign request &mdash;
  &ldquo;write a get-out-the-vote email,&rdquo; &ldquo;draft a thirty-second TV spot,&rdquo; &ldquo;give me a
  contrast line on my opponent&rsquo;s record&rdquo; &mdash; across every channel, and Resonate&rsquo;s own
  engine, which always runs on Grok, writes the draft. We do not change that engine: Grok is the writer,
  exactly as it is in the real product. Second, that finished draft is handed to a council of different AI
  models &mdash; Claude, GPT, Gemini, and others &mdash; but here they are not writers. They are reviewers.
  Each one role-plays a critic with its own standards, reads what Grok produced, and decides whether it meets
  those standards. They never rewrite the draft; they only judge it.</p>
  <p>Every message is tailored to a <strong>specific target segment</strong> &mdash; the group it is written for
  &mdash; and the reviewers score it <strong>for that group</strong>, on the three things a campaign actually
  optimizes when it tailors a message: <strong>(1) message power</strong> &mdash; how strong and compelling it is
  for its target; <strong>(2) tailoring</strong> &mdash; whether it genuinely lands for that specific group rather
  than reading generic or stereotyped; and <strong>(3) a safety guardrail</strong> &mdash; whether anything is
  heinous, cringe, false, or could be clipped and used against the campaign if it surfaced beyond the target. A
  message is <em>not</em> penalized for failing to court groups outside its target &mdash; that is the point of
  tailoring, not a flaw. The first two axes reward and set the headline 0&ndash;100 score; the guardrail is a hard
  cap, so a genuine liability pulls the score down no matter how good the writing. The five models
  <strong>rotate across the three axes every simulation</strong>, so over a run every model scores every axis and
  no single model&rsquo;s bias colours any one axis &mdash; a panel far harder to fool than any single critic.</p>

  <h3 style="font-size:1.05rem; margin:1.4em 0 .4em;">What it checks &mdash; two kinds of review</h3>
  <p>The platform examines Grok&rsquo;s draft in two ways. The first is a set of instant, black-and-white rule
  checks that need no opinion: did the draft leave a template placeholder in the final text, like
  &ldquo;[INSERT NAME]&rdquo;? Did it invent a website link, phone number, or event detail that nobody gave it?
  Is it too long for the format &mdash; an SMS over the limit, or a script that runs past its thirty-second
  slot? Did it drop the legally required &ldquo;Paid for by&rdquo; disclaimer, or word it weakly? These are
  objective, so they run on every draft for free.</p>
  <p>The second kind is the council described above: the five models <strong>score the draft 0&ndash;100 on the
  three axes &mdash; power, tailoring, and the safety guardrail &mdash; for its target segment</strong>, each
  flagging any concern in a sentence and offering <strong>one concrete way to improve it</strong>, judging broadly
  (including whether the platform asked the right clarifying questions first). Power and tailoring set the score;
  the guardrail caps it. Nowhere does anything rewrite the draft: the platform reviews what Grok produced and tells
  your team how to make it better &mdash; your team applies the fixes.</p>

  <h3 style="font-size:1.05rem; margin:1.4em 0 .4em;">Run at scale, and run safely</h3>
  <p>This does not happen once. It runs across every combination of model, persona, channel, and request type,
  repeated as many times as you choose &mdash; so that rare, intermittent failures surface, not just the
  obvious ones a quick demo would catch. The whole thing is bounded by hard spending limits, set by you, so it
  can never cost more than you have allowed; when the ceiling is reached, it simply stops. And it is sealed off
  from the real world by design: the platform only ever asks Resonate to <em>write</em> drafts, and it is
  blocked at multiple independent levels from ever sending a message to an actual voter. Nothing here can touch
  a live campaign, an inbox, or a phone.</p>

  <h3 style="font-size:1.05rem; margin:1.4em 0 .4em;">How the results are organized &mdash; the page you&rsquo;re about to see</h3>
  <p>The next page is built to carry you from thousands of individual results down to the handful of patterns
  that actually matter, quickly. At the very top are the headline numbers: how many messages were tested, how
  many were flagged, the <strong>average quality score (0&ndash;100)</strong> the reviewers gave, and how much
  the testing cost. Directly below, &ldquo;What went wrong, most important first&rdquo; gathers every problem
  into plain-English issues, each ranked by how serious and how frequent it is. Next, &ldquo;Results broken
  down&rdquo; cuts the findings three ways: <strong>by reviewer</strong> (the average score each gave and how
  many concerns it raised), by channel, and by request type. After that, &ldquo;Every simulated message&rdquo;
  lists each test with a <strong>Surface column telling you which chatbox it came from</strong> and its quality
  score; open any one to see the clarifying questions the platform asked, the objective issues, and each
  reviewer&rsquo;s score and suggestion. A &ldquo;How to improve&rdquo; digest collects the reviewers&rsquo;
  concrete suggestions across the batch. Two more pages round it out: a Configure page where you or your
  cofounders can edit the reviewers and checks without touching code, and a Trends page tracking whether quality
  climbs run over run.</p>

  <p style="margin-top:1.4em;"><strong>In short:</strong> this platform exercises Resonate the way thousands of
  real campaigns would, judges what comes out with a diverse and independent panel, and hands you the results
  already sorted by what to fix first &mdash; all before a single word reaches a real voter.</p>

</div>
"""


@st.cache_data(ttl=5)
def load(run_id: int):
    s = Store(DB_PATH)
    return s.sims_for_run(run_id), s.findings_for_run(run_id), s.clusters_for_run(run_id)


# Friendly labels for the five council models (the keys stored in reviews_json / cost summary).
MODEL_LABELS = {
    "claude": "Claude (Anthropic)", "gpt": "GPT (OpenAI)", "gemini": "Gemini (Google)",
    "grok": "Grok (xAI)", "kimi": "Kimi (Moonshot)",
}


def model_label(m: str) -> str:
    return MODEL_LABELS.get(m, m or "—")


def breakdown(df: pd.DataFrame, col: str, humanizer=None) -> pd.DataFrame:
    d = df.copy()
    d[col] = d[col].replace("", "—")
    d["is_flagged"] = d["severity"] != "pass"
    g = d.groupby(col).agg(sims=("sim_id", "count"), flagged=("is_flagged", "sum")).reset_index()
    g["clean_%"] = ((g["sims"] - g["flagged"]) / g["sims"] * 100).round().astype(int)
    if humanizer:
        g[col] = g[col].map(lambda x: humanizer(x) if x != "—" else x)
    return g.sort_values("clean_%")


def reviews_of(df: pd.DataFrame) -> pd.DataFrame:
    """Flatten the per-message reviews_json into rows for aggregation."""
    cols = ["sim_id", "reviewer", "model", "score", "verdict", "concern", "improve"]
    if df.empty or "reviews_json" not in df.columns:
        return pd.DataFrame(columns=cols)
    rows = []
    for _, r in df.iterrows():
        try:
            for rev in json.loads(r.get("reviews_json") or "[]"):
                rows.append({"sim_id": r["sim_id"], **{k: rev.get(k) for k in cols[1:]}})
        except Exception:
            pass
    return pd.DataFrame(rows, columns=cols)


# ══════════════════════════════════════════════════════════════════════════════
# RESULTS
# ══════════════════════════════════════════════════════════════════════════════
def page_results(store: Store) -> None:
    runs = store.list_runs()
    st.title("🧭 Resonate Simulation Harness")
    st.caption("How Grok's draft messages hold up before a real campaign — read by a council of reviewers "
               "against their own standards, and broken down by reviewer, channel, and request type.")
    if not runs:
        st.warning("No runs yet. Generate one:  `python3 scripts/run.py --config configs/example.harness.toml`")
        return

    run_labels = {f"Run {r['id']} · {humanize_mode(r['mode'])} · {r['sim_count']} messages": r for r in runs}
    run = run_labels[st.sidebar.selectbox("Run", list(run_labels))]
    sims, findings, clusters = load(run["id"])
    sims_df, find_df = pd.DataFrame(sims), pd.DataFrame(findings)

    st.sidebar.subheader("Filters")
    def opts(c):
        return sorted(x for x in sims_df[c].fillna("").replace("", "—").unique()) if not sims_df.empty else []
    fc = st.sidebar.multiselect("Channel", opts("channel"))
    fi = st.sidebar.multiselect("Request type", [humanize_intent(x) for x in opts("intent_type")])
    fs = st.sidebar.multiselect("Result", ["critical", "high", "medium", "low", "pass"])

    view = sims_df.copy()
    if not view.empty:
        if fc:
            view = view[view["channel"].isin(fc)]
        if fi:
            view = view[view["intent_type"].map(humanize_intent).isin(fi)]
        if fs:
            view = view[view["severity"].isin(fs)]

    cfg = json.loads(run.get("config") or "{}")
    total = len(view)
    flagged = int((view["severity"] != "pass").sum()) if total else 0
    avg_q = view["quality_score"].dropna() if total and "quality_score" in view.columns else pd.Series(dtype=float)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Messages", total)
    c2.metric("Flagged", flagged)
    c3.metric("Clean", f"{round(100 * (total - flagged) / total) if total else 0}%")
    c4.metric("Avg quality", f"{round(avg_q.mean())}/100" if len(avg_q) else "—")
    c5.metric("Total cost", f"${cfg.get('total_usd', cfg.get('council_spent_usd', 0.0)):.4f}")
    st.divider()

    st.markdown("**💵 What this run cost**")
    council_cost = cfg.get("council_spent_usd", 0.0)
    backend_cost = cfg.get("backend_spent_usd", 0.0)
    total_cost = cfg.get("total_usd", council_cost + backend_cost)
    cc1, cc2, cc3, cc4 = st.columns(4)
    cc1.metric("Total", f"${total_cost:.4f}")
    cc2.metric("Reviewers", f"${council_cost:.4f}", help=f"your council keys · cap ${cfg.get('council_cap_usd', '—')}")
    cc3.metric("Grok drafting", f"${backend_cost:.4f}", help=f"the platform's own spend · cap ${cfg.get('backend_cap_usd', '—')}")
    cc4.metric("Per message", f"${(total_cost / total):.4f}" if total else "$0.0000")
    by_service = cfg.get("backend_by_service") or {}
    by_model = cfg.get("council_by_model") or {}
    per_cap = cfg.get("per_model_cap_usd")
    if by_service or by_model or council_cost:
        rows = [{"What": f"Grok drafting · {k}", "Cost": f"${v:.4f}", "Cap": f"${cfg.get('backend_cap_usd', '—')}"}
                for k, v in sorted(by_service.items(), key=lambda kv: -kv[1])]
        if by_model:
            for m, v in sorted(by_model.items(), key=lambda kv: -kv[1]):
                rows.append({"What": f"Reviewer · {model_label(m)}", "Cost": f"${v:.4f}",
                             "Cap": f"${per_cap}" if per_cap else "—"})
        else:
            rows.append({"What": "Reviewers (council, all providers)", "Cost": f"${council_cost:.4f}", "Cap": "—"})
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.caption("Each of the five models is a separate reviewer ledger (your council keys, billed to you, capped per "
               "model). Grok drafting is the platform's own spend, on its own cap. Both are hard ceilings — the run "
               "stops if it would exceed them.")
    st.divider()

    st.subheader("What went wrong, most important first")
    if clusters:
        cl = pd.DataFrame(clusters)
        cl["Severity"] = cl["severity"].map(humanize_severity)
        cl["Issue"] = cl["dimension"].map(label)
        cl["What it means"] = cl["dimension"].map(describe)
        cl = cl.sort_values("size", ascending=False)
        st.dataframe(cl[["Severity", "Issue", "size", "What it means"]].rename(columns={"size": "How many"}),
                     use_container_width=True, hide_index=True)
    else:
        st.success("Nothing went wrong in this run. 🎉")

    # Click into any finding to read every instance, in plain English.
    st.markdown("**🔎 Explore a finding — click in for every instance, in plain English**")
    fdf = find_df[find_df["sim_id"].isin(view["sim_id"])].copy() if (not find_df.empty and not view.empty) else pd.DataFrame()
    if fdf.empty:
        st.caption("No findings to explore in the current view.")
    else:
        msg_of = {sid: f"Message {i + 1}" for i, sid in enumerate(view.reset_index(drop=True)["sim_id"])}
        surface_of = dict(zip(view["sim_id"], view["surface"].replace("", "—"))) if "surface" in view.columns else {}
        counts = fdf["dimension"].value_counts()
        opt_to_dim = {f"{label(d)}  ({n})": d for d, n in counts.items()}
        pick_f = st.selectbox("Pick an issue to expand", ["—"] + list(opt_to_dim))
        if pick_f != "—":
            dim = opt_to_dim[pick_f]
            st.info(f"**What this means:** {describe(dim)}")
            sub = fdf[fdf["dimension"] == dim].copy()
            sub["Message"] = sub["sim_id"].map(msg_of).fillna(sub["sim_id"])
            sub["Surface"] = sub["sim_id"].map(surface_of).fillna("—") if surface_of else "—"
            sub["Severity"] = sub["severity"].map(humanize_severity)
            sub["Who flagged it"] = sub["source"].map(humanize_source) if "source" in sub.columns else "—"
            tbl = sub[["Message", "Surface", "Severity", "Who flagged it", "detail"]].rename(
                columns={"detail": "What happened (plain English)"})
            st.dataframe(tbl, use_container_width=True, hide_index=True)
            if "evidence" in sub.columns:
                ev = sub[sub["evidence"].astype(str).str.strip().ne("")]
                if not ev.empty:
                    with st.expander(f"Evidence / excerpts ({len(ev)})"):
                        for _, r in ev.iterrows():
                            st.markdown(f"- **{msg_of.get(r['sim_id'], r['sim_id'])}**: {r['evidence']}")
    st.divider()

    st.subheader("Results broken down")
    if not view.empty:
        rv = reviews_of(view)
        if not rv.empty:
            rv["flag"] = rv["verdict"].isin(["concern", "fail"])
        col_job, col_model = st.columns(2)
        with col_job:
            st.markdown("**By scoring axis** — power · tailoring · guardrail")
            if rv.empty:
                st.caption("Reviewer scores appear after a live run with reviewers turned on.")
            else:
                rb = rv.groupby("reviewer").agg(avg=("score", "mean"), Concerns=("flag", "sum")).reset_index()
                rb["Avg score"] = rb["avg"].round().astype("Int64")
                rb = rb.rename(columns={"reviewer": "Job"})[["Job", "Avg score", "Concerns"]].sort_values("Avg score")
                st.bar_chart(rb.set_index("Job")["Avg score"], height=200)
                st.dataframe(rb, use_container_width=True, hide_index=True)
        with col_model:
            st.markdown("**By model** — each rotates across the 3 axes")
            if rv.empty or "model" not in rv or rv["model"].isna().all():
                st.caption("Per-model scores appear after a live run with the rotating council.")
            else:
                mb = (rv.dropna(subset=["model"]).groupby("model")
                      .agg(avg=("score", "mean"), Reviews=("score", "count"), Concerns=("flag", "sum")).reset_index())
                mb["Avg score"] = mb["avg"].round().astype("Int64")
                mb["Model"] = mb["model"].map(model_label)
                mb = mb[["Model", "Avg score", "Reviews", "Concerns"]].sort_values("Avg score")
                st.bar_chart(mb.set_index("Model")["Avg score"], height=200)
                st.dataframe(mb, use_container_width=True, hide_index=True)
        col_ch, col_rt, col_seg = st.columns(3)
        rows3 = [(col_ch, "channel", "Channel"), (col_rt, "intent_type", "Request type")]
        if "target_segment" in view.columns:
            rows3.append((col_seg, "target_segment", "Target segment"))
        for box, col, head in rows3:
            with box:
                st.markdown(f"**By {head.lower()}**")
                hz = humanize_channel if col == "channel" else (humanize_intent if col == "intent_type" else None)
                g = breakdown(view, col, hz)
                st.bar_chart(g.set_index(col)["clean_%"], height=200)
                st.dataframe(g.rename(columns={col: head, "sims": "Messages", "flagged": "Flagged",
                                               "clean_%": "Clean %"}), use_container_width=True, hide_index=True)
        st.caption("Every message is scored on three axes (power, tailoring, guardrail) by models in rotating "
                   "roles, **for its target segment** — power + tailoring drive the score; the guardrail caps it.")
    st.divider()

    st.subheader("Every simulated message")
    if not view.empty:
        view = view.reset_index(drop=True)
        view["Message"] = [f"Message {i + 1}" for i in range(len(view))]
        disp = pd.DataFrame({
            "Message": view["Message"],
            "Surface": view["surface"].replace("", "—") if "surface" in view.columns else "—",
            "Target": view["target_segment"].replace("", "—") if "target_segment" in view.columns else "—",
            "Result": view["severity"].map(humanize_severity),
            "Quality": view["quality_score"].map(lambda x: f"{int(x)}/100" if pd.notna(x) else "—")
            if "quality_score" in view.columns else "—",
            "Channel": view["channel"].map(humanize_channel),
            "Request type": view["intent_type"].map(humanize_intent),
            "Issues": view["finding_count"],
        })
        st.dataframe(disp, use_container_width=True, hide_index=True)

        id_map = dict(zip(view["Message"], view["sim_id"]))
        pick = st.selectbox("Open a message", ["—"] + list(view["Message"]))
        if pick != "—":
            sid = id_map[pick]
            srow = view[view["sim_id"] == sid].iloc[0]
            try:
                qa = json.loads(srow.get("preflight_qa_json") or "[]")
            except Exception:
                qa = []
            if qa:
                st.markdown("**Clarifying questions the platform asked first**")
                for x in qa:
                    st.markdown(f"- *{x.get('q', '')}* → {x.get('a', '')}")
            st.markdown("**Objective checks**")
            obj = find_df[(find_df["sim_id"] == sid) & (find_df["dimension"] != "reviewer_concern")] \
                if not find_df.empty else pd.DataFrame()
            if obj.empty:
                st.caption("Passed every objective check that's turned on.")
            for _, r in obj.iterrows():
                st.markdown(f"- {SEV_EMOJI.get(r['severity'], '')} **{label(r['dimension'])}** — {r['detail']}"
                            + (f"  \n  ↳ {r['evidence']}" if r["evidence"] else ""))
            st.markdown("**Reviewer scores & suggestions**")
            rv1 = reviews_of(view)
            rv1 = rv1[rv1["sim_id"] == sid] if not rv1.empty else rv1
            if rv1.empty:
                st.caption("Reviewer scores appear after a live run.")
            for _, r in rv1.iterrows():
                icon = {"meets": "✅", "fail": "🔴"}.get(r.get("verdict"), "🟠")
                sc = f"{int(r['score'])}/100" if pd.notna(r.get("score")) else "—"
                played = f" _(played by {model_label(r.get('model'))})_" if r.get("model") else ""
                line = f"- {icon} **{r['reviewer']}**{played} · {sc}"
                if r.get("concern"):
                    line += f" · concern: {r['concern']}"
                if r.get("improve"):
                    line += f"  \n  ↳ 💡 {r['improve']}"
                st.markdown(line)

    # Reward side — the best of the run, as exemplars.
    if not view.empty and "quality_score" in view.columns and view["quality_score"].notna().any():
        st.divider()
        st.subheader("🏆 Strongest messages — the best of this run")
        st.caption("Highest reviewer quality scores. Use these as exemplars of what's working.")
        order = {sid: f"Message {i + 1}" for i, sid in enumerate(view.reset_index(drop=True)["sim_id"])}
        top = view.dropna(subset=["quality_score"]).copy()
        top["Message"] = top["sim_id"].map(order)
        top["Quality"] = top["quality_score"].round().astype("Int64").astype(str) + "/100"
        top["Surface"] = top["surface"].replace("", "—") if "surface" in top.columns else "—"
        top["Channel"] = top["channel"].map(humanize_channel)
        best = top.sort_values("quality_score", ascending=False).head(5)
        st.dataframe(best[["Message", "Quality", "Surface", "Channel"]], use_container_width=True, hide_index=True)

    if not view.empty:
        rv_all = reviews_of(view)
        improves = [s for s in (rv_all["improve"].tolist() if not rv_all.empty else []) if isinstance(s, str) and s.strip()]
        if improves:
            st.divider()
            st.subheader("💡 How to improve — what the reviewers suggested")
            st.caption("Concrete suggestions across messages. Your team applies the fixes (via Codex/Claude); "
                       "the harness only reviews — it never rewrites or changes the backend.")
            for s in improves[:20]:
                st.markdown(f"- {s}")

    with st.expander("Config used for this run"):
        st.json(cfg)


# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURE  (point-and-click criteria editor — writes a .toml)
# ══════════════════════════════════════════════════════════════════════════════
def page_configure() -> None:
    st.title("⚙️ Configure criteria")
    st.caption("Edit a simulation config without touching code. Save it, then run "
               "`scripts/run_live.py --config configs/<name>.toml`.")

    files = sorted(p.name for p in CONFIG_DIR.glob("*.toml"))
    name_map = {}
    for fn in files:
        try:
            name_map[tomllib.loads((CONFIG_DIR / fn).read_text()).get("name", fn)] = fn
        except Exception:
            name_map[fn] = fn
    if not name_map:
        name_map = {"Example": "example.harness.toml"}
    base = name_map[st.selectbox("Start from", list(name_map))]
    d = tomllib.loads((CONFIG_DIR / base).read_text()) if (CONFIG_DIR / base).exists() else {}
    g = lambda *ks, default=None: _dig(d, ks, default)  # noqa: E731

    st.subheader("Basics")
    name = st.text_input("Name", g("name", default="my-campaign"))
    desc = st.text_input("Description", g("description", default=""))
    base_url = st.text_input("Target backend URL", g("target", "base_url", default="http://localhost:8000"))

    st.subheader("Reviewers — the review council")
    st.caption("Each reviewer is a model role-playing a critic with its OWN standards. They read Grok's draft "
               "and judge it against those standards — they never rewrite it. Add or remove rows; write each "
               "reviewer's standards in plain English (e.g. tolerance for sharp language, rhetoric they like).")
    default_revs = g("reviewers", default=[
        {"name": "Compliance & legal hawk", "model": "judge/sonnet",
         "criteria": "Strict on legal/compliance risk: missing disclaimers, unverified claims, FEC/FCC/TCPA exposure."},
        {"name": "Punchy persuader", "model": "judge/gpt",
         "criteria": "Rewards bold, memorable, emotional copy with a clear ask; flags bland or hedged writing."},
        {"name": "Moderate, broad-appeal", "model": "judge/gemini",
         "criteria": "Flags inflammatory, divisive, or offensive language; prefers a measured, unifying tone."},
    ])
    reviewers_df = pd.DataFrame(default_revs or [], columns=["name", "model", "criteria"])
    edited_reviewers = st.data_editor(
        reviewers_df, num_rows="dynamic", use_container_width=True, key="reviewers_editor",
        column_config={
            "name": st.column_config.TextColumn("Reviewer", width="medium"),
            "model": st.column_config.TextColumn("Model", width="small"),
            "criteria": st.column_config.TextColumn("Their standards (plain English)", width="large"),
        })

    st.subheader("Campaign inputs — variety")
    models = st.text_area("Models used to generate varied campaign requests (one per line)",
                          "\n".join(g("council", "models", default=["council/claude", "council/gpt"])))

    st.subheader("Simulation matrix (how many loops)")
    mc1, mc2 = st.columns(2)
    channels = mc1.multiselect("Channels", ALL_CHANNELS, g("matrix", "channels", default=["email", "sms"]))
    intents = mc2.multiselect("Intents", ALL_INTENTS, g("matrix", "intents", default=["fresh_draft", "revision", "discussion"]))
    mc3, mc4 = st.columns(2)
    repeats = mc3.number_input("Repeats per cell", 1, 50, int(g("matrix", "repeats_per_cell", default=1)))
    max_sims = mc4.number_input("Max sims (cap)", 1, 100000, int(g("matrix", "max_sims", default=50)))

    st.subheader("Budgets (hard caps, USD)")
    bc1, bc2 = st.columns(2)
    council_usd = bc1.number_input("Reviewers + inputs (AI cost)", 0.0, 100000.0, float(g("budgets", "council_usd", default=30.0)))
    backend_usd = bc2.number_input("Grok drafting", 0.0, 100000.0, float(g("budgets", "backend_draft_usd", default=15.0)))

    st.subheader("Rubric — thresholds")
    rc = st.columns(3)
    sms_max = rc[0].number_input("SMS max chars", 1, 5000, int(g("rubric", "sms_max_chars", default=320)))
    slot = rc[1].number_input("Broadcast slot (sec)", 1, 600, int(g("rubric", "broadcast_slot_seconds", default=30)))
    speech_min = rc[2].number_input("Speech min words", 1, 10000, int(g("rubric", "speech_min_words", default=120)))
    rc2 = st.columns(3)
    wps = rc2[0].number_input("Words / second", 0.1, 10.0, float(g("rubric", "words_per_sec", default=2.5)))
    sd_warn = rc2[1].number_input("Stance-drift warn", 0.0, 1.0, float(g("rubric", "stance_drift_warn", default=0.5)))
    sd_high = rc2[2].number_input("Stance-drift high", 0.0, 1.0, float(g("rubric", "stance_drift_high", default=0.75)))

    st.subheader("Which checks are on")
    st.caption("Tick the issues you want the harness to flag. Hover the ⓘ for what each one means.")
    existing_dims = g("rubric", "dimensions", default={})
    dim_cfg = {}
    for dim, scored_by, default_sev in DIMENSIONS:
        cur = existing_dims.get(dim, {})
        col1, col2, col3 = st.columns([3, 1, 2])
        on = col1.checkbox(f"{label(dim)}  ·_{humanize_source(scored_by)}_", value=cur.get("enabled", True),
                           key=f"en_{dim}", help=describe(dim))
        col2.write("")
        sev_default = cur.get("severity", default_sev if default_sev != "(default)" else "(default)")
        sev = col3.selectbox("severity", SEV_OPTS, index=SEV_OPTS.index(sev_default) if sev_default in SEV_OPTS else 0,
                             key=f"sev_{dim}", label_visibility="collapsed")
        entry = {"enabled": on}
        if sev != "(default)":
            entry["severity"] = sev
        dim_cfg[dim] = entry

    st.divider()
    save_name = st.text_input("Save as (filename)", value=name.replace(" ", "-") + ".toml")
    if st.button("💾 Save config", type="primary"):
        out = {
            "name": name, "description": desc,
            "target": {"base_url": base_url, "dev_email": g("target", "dev_email", default="harness-operator@example.com"), "bearer_token": ""},
            "council": {"models": _lines(models)},
            "reviewers": [r for r in edited_reviewers.fillna("").to_dict("records") if str(r.get("name", "")).strip()],
            "matrix": {"channels": channels, "intents": intents, "repeats_per_cell": int(repeats), "max_sims": int(max_sims)},
            "budgets": {"council_usd": council_usd, "backend_draft_usd": backend_usd},
            "flagging": {"cluster": True, "min_severity": "low"},
            "output": {"db_path": "runs/harness.db"},
            "rubric": {"sms_max_chars": int(sms_max), "broadcast_slot_seconds": int(slot), "words_per_sec": wps,
                       "speech_min_words": int(speech_min), "stance_drift_warn": sd_warn, "stance_drift_high": sd_high,
                       "dimensions": dim_cfg},
        }
        fname = save_name if save_name.endswith(".toml") else save_name + ".toml"
        path = CONFIG_DIR / Path(fname).name
        with open(path, "wb") as f:
            tomli_w.dump(out, f)
        st.success(f"Saved → configs/{path.name}.  Run it:  scripts/run_live.py --config configs/{path.name}")
        st.code(tomli_w.dumps(out), language="toml")


# ══════════════════════════════════════════════════════════════════════════════
# TRENDS
# ══════════════════════════════════════════════════════════════════════════════
def page_trends(store: Store) -> None:
    st.title("📈 Trends across runs")
    runs = store.list_runs()
    if not runs:
        st.warning("No runs yet.")
        return
    df = pd.DataFrame(runs)
    df["clean_%"] = ((df["sim_count"] - df["flagged"]) / df["sim_count"].clip(lower=1) * 100).round().astype(int)
    df = df.sort_values("id")
    st.caption("Each point is a run. Watch the clean rate climb as the platform improves.")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Clean % over runs**")
        st.line_chart(df.set_index("id")["clean_%"], height=240)
    with c2:
        st.markdown("**Flagged messages over runs**")
        st.bar_chart(df.set_index("id")["flagged"], height=240)
    table = df.copy()
    table["Type"] = table["mode"].map(humanize_mode)
    st.dataframe(table[["id", "Type", "sim_count", "flagged", "clean_%"]].rename(
        columns={"id": "Run", "sim_count": "Messages", "flagged": "Flagged", "clean_%": "Clean %"}),
        use_container_width=True, hide_index=True)


def _dig(d: dict, ks, default):
    cur = d
    for k in ks:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def _lines(text: str) -> list[str]:
    return [ln.strip() for ln in (text or "").splitlines() if ln.strip()]


# ══════════════════════════════════════════════════════════════════════════════
# ABOUT  (mandatory intro — gates entry; also revisitable from the nav)
# ══════════════════════════════════════════════════════════════════════════════
def page_about(gate: bool) -> None:
    st.markdown("<h2 style='margin-bottom:.2em;'>About this platform</h2>", unsafe_allow_html=True)
    st.markdown(ABOUT_HTML, unsafe_allow_html=True)
    if gate:
        st.write("")
        c = st.columns([3, 2, 3])
        if c[1].button("I’ve read this — enter the dashboard →", type="primary", use_container_width=True):
            st.session_state["entered"] = True
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# FOR COFOUNDERS  (run-your-own guide, rendered from COFOUNDERS.md)
# ══════════════════════════════════════════════════════════════════════════════
def page_cofounders() -> None:
    st.title("👥 For cofounders — run your own")
    st.caption("How to run your own simulations, billed to your own API keys. "
               "Each person runs locally with their own keys; results publish to a shared link.")
    for fname in ("COFOUNDERS.md", "DEPLOY.md"):
        path = ROOT / fname
        try:
            text = path.read_text()
        except Exception:
            continue
        if fname == "DEPLOY.md":
            with st.expander("📡 Deploying / sharing the dashboard (DEPLOY.md)"):
                st.markdown(text)
        else:
            st.markdown(text)
    st.divider()
    st.caption("Full source + these docs live in the GitHub repo.")


# ── router ────────────────────────────────────────────────────────────────────
st.sidebar.title("🧭 Sim Harness")

# Mandatory intro: must be read (and acknowledged) on every fresh visit before entering.
if not st.session_state.get("entered"):
    page_about(gate=True)
    st.stop()

page = st.sidebar.radio("View", ["📊 Results", "⚙️ Configure", "📈 Trends", "👥 Cofounders", "ℹ️ About"],
                        label_visibility="collapsed")
st.sidebar.divider()
_store = Store(DB_PATH)
if page.startswith("📊"):
    page_results(_store)
elif page.startswith("⚙️"):
    page_configure()
elif page.startswith("📈"):
    page_trends(_store)
elif page.startswith("👥"):
    page_cofounders()
else:
    page_about(gate=False)
