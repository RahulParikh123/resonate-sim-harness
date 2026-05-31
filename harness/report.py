"""Shared console reporting — cluster triage, per-model / per-persona breakdowns,
and the plain-English layer legend. Used by both run.py and run_live.py."""

from __future__ import annotations

from .flagging import Cluster, SimVerdict, summarize_by
from .labels import humanize_channel, humanize_intent, label
from .schemas import Severity

ICON = {Severity.CRITICAL: "⛔", Severity.HIGH: "🔴", Severity.MEDIUM: "🟠", Severity.LOW: "🟡"}


def print_clusters(clusters: list[Cluster]) -> None:
    print("  Triage — clusters by severity × frequency:")
    print("  " + "─" * 68)
    for c in clusters:
        chans = ", ".join(f"{humanize_channel(k)}×{n}" for k, n in sorted(c.channels.items(), key=lambda kv: -kv[1]))
        ev = f'  e.g. "{c.example_evidence}"' if c.example_evidence else ""
        print(f"  {ICON[c.severity]} {c.severity.value.upper():<8} {label(c.dimension)}  (×{c.size})  [{chans}]{ev}")


def _breakdown(title: str, groups: dict) -> None:
    print(f"\n  {title}")
    for k, g in sorted(groups.items(), key=lambda kv: kv[1]["pass_rate"]):
        sev = " ".join(f"{ICON[Severity(s)]}{n}" for s, n in sorted(g["severities"].items(), key=lambda x: -x[1]))
        print(f"    {k:<40} {g['flagged']}/{g['total']} flagged · {g['pass_rate']:>3}% clean   {sev}")


def print_breakdowns(verdicts: list[SimVerdict]) -> None:
    _breakdown("By channel:", summarize_by(verdicts, lambda v: humanize_channel(v.channel)))
    _breakdown("By request type:", summarize_by(verdicts, lambda v: humanize_intent(v.intent_type)))


def print_legend() -> None:
    print("\n  How to read this — the layers that produced it (plain English):")
    print("    1. Request    a realistic campaign ask (with clarifying questions, if enabled) goes in.")
    print("    2. Grok       the platform drafts the message — unchanged.")
    print("    3. Checks     instant objective rule-checks catch hard failures (free, fast).")
    print("    4. Reviewers  a council proxying different voters scores 0–100 + suggests how to improve.")
    print("    5. Flagging   problems grouped + ranked; suggestions collected. Reviewers never rewrite.")
    print("    Full write-up → HOW-IT-WORKS.md")
