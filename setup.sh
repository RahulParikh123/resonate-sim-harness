#!/usr/bin/env bash
# One-command setup for running the harness locally on your own keys.
#   bash setup.sh
# Safe to re-run. Sets up the harness Python env + your .env, and brings up the
# local Resonate backend if it's present at ~/resonate-staging.
set -euo pipefail

HARNESS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${HOME}/resonate-harness-venv"
BACKEND="${RESONATE_BACKEND:-${HOME}/resonate-staging}"

echo "▸ Checking prerequisites…"
command -v uv     >/dev/null || { echo "  ✗ 'uv' not found — install from https://docs.astral.sh/uv"; exit 1; }
command -v docker >/dev/null || echo "  ! 'docker' not found — only needed to run the local backend."
echo "  ✓ ok"

echo "▸ Setting up the harness Python environment ($VENV)…"
uv venv --python 3.13 "$VENV" >/dev/null 2>&1 || true
uv pip install --python "$VENV/bin/python" -q httpx litellm pandas streamlit tomli-w python-dotenv
echo "  ✓ dependencies installed"

echo "▸ Preparing your keys file…"
if [ ! -f "$HARNESS_DIR/.env" ]; then
  cp "$HARNESS_DIR/.env.example" "$HARNESS_DIR/.env"
  echo "  ✓ created resonate-sim-harness/.env — OPEN IT AND PASTE YOUR COUNCIL/REVIEWER KEYS"
else
  echo "  ✓ resonate-sim-harness/.env already exists"
fi

echo "▸ Local backend…"
if [ -f "$BACKEND/docker-compose.yml" ]; then
  [ -f "$BACKEND/.env.local" ] || { [ -f "$BACKEND/.env.example" ] && cp "$BACKEND/.env.example" "$BACKEND/.env.local"; }
  docker compose -f "$BACKEND/docker-compose.yml" up -d postgres redis backend >/dev/null 2>&1 \
    && echo "  ✓ backend stack up at http://localhost:8000 (set XAI/ANTHROPIC key in $BACKEND/.env.local for drafting)" \
    || echo "  ! couldn't start the backend — is Docker running? (or point a config at a shared staging URL)"
else
  echo "  ! no backend at $BACKEND — clone the Resonate repo there, or set RESONATE_BASE_URL in your config to a shared staging URL."
fi

cat <<EOF

✅ Setup done. Next:
  1. Paste your keys:
       - council/reviewer keys → resonate-sim-harness/.env
       - backend draft key (XAI or ANTHROPIC) → ${BACKEND}/.env.local
  2. Run a simulation:
       $VENV/bin/python scripts/run_live.py --config configs/quick-smoke.toml --preflight --review
  3. View results:
       $VENV/bin/streamlit run dashboard/app.py        # http://localhost:8501

Presets: quick-smoke · example.harness · full-sweep   (or build your own in the Configure page)
Full guide: COFOUNDERS.md
EOF
