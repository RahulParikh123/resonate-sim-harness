"""Pull the backend's drafting spend for a run from Resonate's spend_events table.

The harness creates a fresh project per run, so spend_events rows for that project_id
are exactly that run's backend (Grok drafting) cost. Council/reviewer spend is tracked
separately by the harness's own Budget (LiteLLM). Together they're the run's total.
"""

from __future__ import annotations

import os

# Local docker-compose Postgres (resonate:resonate@localhost:5432/resonate_dev).
DEFAULT_DB = os.environ.get("BACKEND_DB_URL", "postgresql://resonate:resonate@localhost:5432/resonate_dev")


def backend_spend(project_id: str, db_url: str | None = None) -> dict | None:
    """Return {"total_usd": float, "by_service": {service: usd}} for a project's backend
    LLM spend, or None if the DB isn't reachable (e.g. dry run / no driver)."""
    try:
        import psycopg
    except Exception:
        return None
    try:
        with psycopg.connect(db_url or DEFAULT_DB, connect_timeout=5) as conn:
            rows = conn.execute(
                "SELECT service, COALESCE(SUM(amount_cents), 0) FROM spend_events "
                "WHERE project_id = %s::uuid GROUP BY service",
                (str(project_id),),
            ).fetchall()
    except Exception:
        return None
    by_service = {svc: round(cents / 100.0, 4) for svc, cents in rows}
    return {"total_usd": round(sum(by_service.values()), 4), "by_service": by_service}
