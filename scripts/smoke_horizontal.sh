#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
if docker compose ps --status running api | grep -q api; then
  docker compose exec -T api python scripts/smoke_demo.py
elif [[ -x .venv/bin/python ]] && .venv/bin/python -c "import fastapi" >/dev/null 2>&1; then
  PYTHONPATH=. .venv/bin/python scripts/smoke_demo.py
else
  echo "Start Docker with 'docker compose up -d' or install the API requirements in a local virtualenv." >&2
  exit 1
fi
