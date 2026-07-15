#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
./scripts/setup_local.sh
docker compose up --build -d
curl --fail --silent --show-error http://localhost:"${API_PORT:-8000}"/health
echo
curl --fail --silent --show-error http://localhost:"${API_PORT:-8000}"/setup/status
echo
curl --fail --silent --show-error http://localhost:"${WEB_PORT:-3000}"/ >/dev/null
docker compose exec -T api python scripts/check_real_setup.py
echo "Stack and core processing checks passed. Open http://localhost:${WEB_PORT:-3000}."
