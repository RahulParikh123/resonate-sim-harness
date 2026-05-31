"""LiteLLM wrapper — one call path for the council + judges.

Provides: robust JSON parsing, a hard budget cap (raises when exhausted), and
graceful cost accounting. litellm is imported lazily so the rest of the harness
imports without it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

_FENCE = re.compile(r"^```[a-zA-Z]*\n?|\n?```$")

# Friendly council/reviewer names → real LiteLLM model IDs (in-process, no proxy).
# IDs below were live-verified against the project's keys on 2026-05-30. If a provider
# rolls a model, re-run scripts/check_models.py and update here — a stale ID 404s.
MODEL_MAP = {
    # ── the five-model council: one model per provider (the diversity backbone) ──
    "claude": "anthropic/claude-haiku-4-5",      # Anthropic
    "gpt":    "openai/gpt-4o-mini",              # OpenAI
    "gemini": "gemini/gemini-2.5-flash",         # Google
    "grok":   "xai/grok-3",                      # xAI
    "kimi":   "moonshot/moonshot-v1-8k",         # Moonshot
    # higher-fidelity variants — swap in for fewer, sharper runs.
    "claude-pro": "anthropic/claude-sonnet-4-5",
    "gpt-pro":    "openai/gpt-4o",
    "gemini-pro": "gemini/gemini-2.5-pro",
    # ── backward-compatible aliases (older configs / tests) ──
    "council/claude": "anthropic/claude-haiku-4-5",
    "council/gpt":    "openai/gpt-4o-mini",
    "council/gemini": "gemini/gemini-2.5-flash",
    "council/kimi":   "moonshot/moonshot-v1-8k",
    "council/grok":   "xai/grok-3",
    "judge/sonnet":   "anthropic/claude-sonnet-4-5",
    "judge/gpt":      "openai/gpt-4o",
    "judge/gemini":   "gemini/gemini-2.5-pro",
}


# The five-model council — display label → friendly key (resolved via MODEL_MAP).
# This is the diversity backbone: each provider is one independent "voice", and the
# rotation logic assigns these five to the review jobs differently every simulation.
COUNCIL_MODELS = {
    "Anthropic": "claude",
    "OpenAI":    "gpt",
    "Google":    "gemini",
    "xAI":       "grok",
    "Moonshot":  "kimi",
}


def resolve_model(model: str) -> str:
    return MODEL_MAP.get(model, model)


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class Budget:
    """Hard USD ceiling enforced PER MODEL. When a model hits its cap, further calls
    to it raise BudgetExceeded (callers skip that reviewer). Belt-and-suspenders
    alongside the per-provider caps you set in each provider dashboard."""
    per_model_cap: float
    spent_by_model: dict = field(default_factory=dict)
    overrides: dict = field(default_factory=dict)  # model -> its own cap
    calls: int = 0

    def cap_for(self, model: str) -> float:
        return self.overrides.get(model, self.per_model_cap)

    def check(self, model: str) -> None:
        if self.spent_by_model.get(model, 0.0) >= self.cap_for(model):
            raise BudgetExceeded(f"{model} hit its ${self.cap_for(model):.2f} cap")

    def add(self, model: str, usd: float | None) -> None:
        self.spent_by_model[model] = self.spent_by_model.get(model, 0.0) + max(0.0, float(usd or 0.0))
        self.calls += 1

    @property
    def spent_usd(self) -> float:
        return round(sum(self.spent_by_model.values()), 4)


# Fallback list prices (USD per 1M tokens, input/output) for when LiteLLM has no price
# for a model ID. Without this, cheap models register as $0 — which both understates the
# bill AND silently disables their per-model budget cap. Approximate; tune as needed.
_FALLBACK_PRICING = {
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-sonnet-4-5": (3.0, 15.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-4-1": (15.0, 75.0),
    "claude-opus-4-8": (15.0, 75.0),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.5, 10.0),
    "gpt-5": (1.25, 10.0),
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-pro": (1.25, 10.0),
    "grok-3": (3.0, 15.0),
    "grok-4": (3.0, 15.0),
    "moonshot-v1": (0.84, 0.84),
    "kimi": (0.84, 0.84),
}


def _estimate_cost(model_id: str, resp) -> float:
    """Best-effort cost from token usage when litellm.completion_cost returns 0."""
    try:
        pin = int(resp.usage.prompt_tokens or 0)
        pout = int(resp.usage.completion_tokens or 0)
    except Exception:
        return 0.0
    for key, (cin, cout) in _FALLBACK_PRICING.items():
        if key in model_id:
            return round((pin * cin + pout * cout) / 1_000_000.0, 6)
    return 0.0


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
        budget.check(model)
    kwargs: dict = {
        "model": resolve_model(model),
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
    if cost <= 0.0:  # litellm has no price for this ID → estimate so the bill + cap stay real
        cost = _estimate_cost(resolve_model(model), resp)
    if budget:
        budget.add(model, cost)
    return text, cost
