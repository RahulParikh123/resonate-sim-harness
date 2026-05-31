"""Pull the backend's drafting spend for a run from Resonate's spend_events table.

The harness creates a fresh project per run, so spend_events rows for that project_id
are exactly that run's backend (Grok drafting) cost. Council/reviewer spend is tracked
separately by the harness's own Budget (LiteLLM). Together they're the run's total.

Reaching the database is the fiddly part. The backend talks to Postgres over the Docker
network (host ``postgres``), which isn't reachable from your laptop. The published port
(localhost:5432) often collides with a Postgres you already run locally — connecting there
silently hits the WRONG database. So we try, in order:

  1. BACKEND_DB_URL (set this to override everything — e.g. on a cloud/Linux host).
  2. A direct connection to localhost:5432 (works when nothing else squats that port).
  3. ``docker exec`` straight into the Postgres container (works regardless of host-port
     collisions — this is the path that "just works" on a typical laptop dev stack).

Any step that fails falls through to the next; if all fail we return None and the caller
shows $0 with a note. Set BACKEND_DB_URL to skip the guessing.
"""

from __future__ import annotations

import os
import re
import subprocess
import uuid

# Local docker-compose Postgres (resonate:resonate@localhost:5432/resonate_dev).
DEFAULT_DB = os.environ.get("BACKEND_DB_URL", "postgresql://resonate:resonate@localhost:5432/resonate_dev")
_PG_USER = os.environ.get("BACKEND_DB_USER", "resonate")
_PG_NAME = os.environ.get("BACKEND_DB_NAME", "resonate_dev")

_SPEND_SQL = (
    "SELECT service, COALESCE(SUM(amount_cents), 0) FROM spend_events "
    "WHERE project_id = '{pid}'::uuid GROUP BY service"
)


def _valid_uuid(pid: str) -> bool:
    try:
        uuid.UUID(str(pid))
        return True
    except Exception:
        return False


def _rows_to_result(rows) -> dict:
    by_service = {svc: round(int(cents) / 100.0, 4) for svc, cents in rows}
    return {"total_usd": round(sum(by_service.values()), 4), "by_service": by_service}


def _via_psycopg(project_id: str, db_url: str) -> dict | None:
    """Direct TCP connection. Returns None on ANY failure (driver missing, port
    collision with a local Postgres, auth/role mismatch, …) so we can fall through."""
    try:
        import psycopg
    except Exception:
        return None
    try:
        with psycopg.connect(db_url, connect_timeout=5) as conn:
            rows = conn.execute(
                "SELECT service, COALESCE(SUM(amount_cents), 0) FROM spend_events "
                "WHERE project_id = %s::uuid GROUP BY service",
                (str(project_id),),
            ).fetchall()
        return _rows_to_result(rows)
    except Exception:
        return None


def _find_pg_container() -> str | None:
    """Best-effort: the Resonate Postgres container name. Prefers a compose service
    labelled ``postgres``; otherwise any running container with 'postgres' in its name,
    preferring one that looks like the resonate stack."""
    for args in (
        ["docker", "ps", "--filter", "label=com.docker.compose.service=postgres", "--format", "{{.Names}}"],
        ["docker", "ps", "--filter", "name=postgres", "--format", "{{.Names}}"],
    ):
        try:
            out = subprocess.run(args, capture_output=True, text=True, timeout=10)
        except Exception:
            continue
        names = [n.strip() for n in (out.stdout or "").splitlines() if n.strip()]
        if names:
            return next((n for n in names if "resonate" in n.lower()), names[0])
    return None


def _via_docker(project_id: str) -> dict | None:
    """Run the aggregate query inside the Postgres container. Robust to host-port
    collisions because it never touches the host network. Returns None if docker isn't
    available or the container can't be found."""
    if not _valid_uuid(project_id):  # we only ever pass our own bootstrap UUID; guard anyway
        return None
    container = _find_pg_container()
    if not container:
        return None
    sql = _SPEND_SQL.format(pid=str(project_id))
    try:
        out = subprocess.run(
            ["docker", "exec", container, "psql", "-U", _PG_USER, "-d", _PG_NAME,
             "-t", "-A", "-F", ",", "-c", sql],
            capture_output=True, text=True, timeout=20,
        )
    except Exception:
        return None
    if out.returncode != 0:
        return None
    rows = []
    for line in (out.stdout or "").splitlines():
        line = line.strip()
        if not line or "," not in line:
            continue
        svc, _, cents = line.rpartition(",")
        if re.fullmatch(r"-?\d+", cents.strip()):
            rows.append((svc.strip(), int(cents.strip())))
    return _rows_to_result(rows)


def backend_spend(project_id: str, db_url: str | None = None) -> dict | None:
    """Return {"total_usd": float, "by_service": {service: usd}} for a project's backend
    LLM (Grok drafting) spend, or None if the DB can't be reached by any method."""
    url = db_url or DEFAULT_DB
    # 1+2. Direct connection (explicit override, or default localhost).
    result = _via_psycopg(project_id, url)
    if result is not None:
        return result
    # 3. Fall back to querying the container directly (handles the laptop port collision).
    return _via_docker(project_id)
