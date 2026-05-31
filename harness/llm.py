"""LiteLLM wrapper — one call path for the council + judges.

Provides: robust JSON parsing, a hard budget cap (raises when exhausted), and
graceful cost accounting. litellm is imported lazily so the rest of the harness
imports without it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

_FENCE = re.compile(r"^```[a-zA-Z]*\n?|\n?```$")


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class Budget:
    """Hard USD ceiling for council + judge spend. Belt-and-suspenders alongside
    the per-provider caps you set in each dashboard."""
    cap_usd: float
    spent_usd: float = 0.0
    calls: int = 0

    def check(self) -> None:
        if self.spent_usd >= self.cap_usd:
            raise BudgetExceeded(
                f"council/judge budget of ${self.cap_usd:.2f} exhausted (spent ${self.spent_usd:.4f}).")

    def add(self, usd: float | None) -> None:
        self.spent_usd += max(0.0, float(usd or 0.0))
        self.calls += 1


def safe_json(text: str) -> dict | None:
    """Parse JSON from a model response, tolerating markdown fences / surrounding prose."""
    t = _FENCE.sub("", (text or "").strip()).strip()
    try:
        return json.loads(t)
    except Exception:
        m = re.search(r"\{.*\}", t, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
    return None


async def acomplete(model: str, system: str, user: str, *, budget: Budget | None = None,
                    temperature: float = 0.7, max_tokens: int = 1200, json_mode: bool = True) -> tuple[str, float]:
    """Call a model via LiteLLM. Returns (text, cost_usd). Enforces the budget cap."""
    import litellm

    litellm.drop_params = True  # silently drop params a given provider doesn't support
    if budget:
        budget.check()
    kwargs: dict = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    resp = await litellm.acompletion(**kwargs)
    text = resp.choices[0].message.content or ""
    try:
        cost = float(litellm.completion_cost(completion_response=resp) or 0.0)
    except Exception:
        cost = 0.0
    if budget:
        budget.add(cost)
    return text, cost
