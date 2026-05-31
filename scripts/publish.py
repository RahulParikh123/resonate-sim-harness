#!/usr/bin/env python3
"""Publish the latest run to the hosted (always-on) dashboard link.

Copies your local results DB into the committed snapshot the Streamlit Cloud
dashboard reads, then commits + pushes. Streamlit Cloud redeploys on push, so the
public link refreshes within ~1–2 minutes. Run it after a sim run:

    <venv>/bin/python scripts/publish.py

(Nothing secret is published — the snapshot holds run results only, never keys.)
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "runs" / "harness.db"
DST = ROOT / "dashboard" / "published.db"


def _git(*args: str) -> tuple[int, str]:
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()


def main() -> int:
    if not SRC.exists():
        print(f"No results DB at {SRC.relative_to(ROOT)} — run a simulation first.")
        return 1
    DST.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SRC, DST)
    print(f"Copied runs/{SRC.name} → {DST.relative_to(ROOT)}")

    _git("add", "-f", str(DST))
    code, out = _git("commit", "-m", "Publish latest run to the live dashboard")
    if code != 0 and "nothing to commit" in out:
        print("Already up to date — nothing new to publish.")
        return 0
    code, out = _git("push")
    if code != 0:
        print(f"Push failed (check your git auth):\n{out}")
        return 1
    print("✅ Published. The hosted dashboard link refreshes in ~1–2 minutes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
