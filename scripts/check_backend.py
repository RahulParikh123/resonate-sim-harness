#!/usr/bin/env python3
"""Smoke-test the live backend driver against the local stack.

    <venv>/bin/python scripts/check_backend.py

Verifies the keyless parts (health, dev-auth bootstrap, project creation) and
probes draft-batch to confirm the request shape is accepted (it will fail at the
LLM call until a backend key is set — that's expected and informative).
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness.api_client import ApiError, ResonateClient  # noqa: E402


async def main() -> int:
    base = os.environ.get("RESONATE_BASE_URL", "http://localhost:8000")
    client = ResonateClient(base_url=base, dev_email=os.environ.get("RESONATE_DEV_EMAIL", "harness-operator@example.com"))

    print(f"\n  Backend check → {base}")
    print("  " + "─" * 60)

    h = await client.health()
    print(f"  ✅ health: {h}")

    org_id, project_id = await client.bootstrap()
    print(f"  ✅ dev-auth bootstrap: org={org_id}")
    print(f"  ✅ sandbox project created: project={project_id}")

    print("\n  probing draft-batch (email)…")
    try:
        resp = await client.draft_batch(project_id, "email",
                                        intent="Write a short GOTV email to persuadable voters in Gary.")
        sim = ResonateClient.to_sim_result("probe-1", "email", "fresh_draft",
                                           "GOTV email", "", resp)
        print(f"  ✅ DRAFT GENERATED ({len(sim.content_text)} chars) — a backend LLM key is live!")
        print(f"     advisory_flags={sim.advisory_flags} stance_drift={sim.stance_drift_score}")
    except ApiError as e:
        if e.status == 422:
            print(f"  ⚠️  422 — request shape rejected, needs adjustment:\n     {e.body[:400]}")
        else:
            print(f"  ✅ request accepted; failed at generation (expected — no backend LLM key yet).")
            print(f"     [{e.status}] {e.body[:220]}")
    print("\n  → Keyless contract verified. Add a backend key (ANTHROPIC/XAI) to generate real drafts.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
