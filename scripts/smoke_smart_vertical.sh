#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
if docker compose ps --status running api | grep -q api; then
  docker compose exec -T api python scripts/smoke_smart_vertical.py
elif [[ -x .venv/bin/python ]]; then
  PYTHONPATH=. .venv/bin/python scripts/smoke_smart_vertical.py
else
  PYTHONPATH=. python3 scripts/smoke_smart_vertical.py
fi
