#!/usr/bin/env python3
"""Confirm every council model is actually connected — using the harness's own call
path (resolve_model + acomplete), so a green check here means the real runs will work.

    <venv>/bin/python scripts/check_models.py

Exits 0 only if all five providers answer. Prints a clean table; never prints keys.
Run this whenever you (or a cofounder) add keys, or after a provider rolls a model.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
logging.getLogger("LiteLLM").setLevel(logging.CRITICAL)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=True)  # file keys win over any stale shell vars
except Exception:
    pass

from harness.llm import COUNCIL_MODELS, acomplete, resolve_model  # noqa: E402


async def check(name: str, friendly: str):
    real = resolve_model(friendly)
    try:
        text, _ = await asyncio.wait_for(
            acomplete(friendly, "You are a connectivity check.", "Reply with the single word: ok",
                      temperature=0, max_tokens=5, json_mode=False),
            timeout=45)
        return name, friendly, real, True, (text or "").strip().replace("\n", " ")[:24]
    except Exception as e:
        return name, friendly, real, False, f"{type(e).__name__}: {str(e)[:90]}"


async def main() -> int:
    print("\n  Council connectivity — one tiny live call per model (no keys printed)")
    print("  " + "─" * 72)
    results = await asyncio.gather(*[check(label, fm) for label, fm in COUNCIL_MODELS.items()])
    ok = 0
    for name, friendly, real, success, info in results:
        mark = "✅" if success else "❌"
        if success:
            ok += 1
        print(f"  {mark}  {name:9s} {friendly:8s} → {real:34s} {info}")
    print("  " + "─" * 72)
    print(f"  {ok}/{len(results)} models connected.\n")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
