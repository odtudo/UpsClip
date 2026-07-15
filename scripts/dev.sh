#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -x .venv/bin/uvicorn ]]; then
  echo "Missing .venv. Follow the native setup in README.md first." >&2
  exit 1
fi
if [[ ! -d apps/web/node_modules ]]; then
  echo "Missing frontend dependencies. Run: npm --prefix apps/web install" >&2
  exit 1
fi
export PATH="$ROOT_DIR/.venv/bin:$PATH"

cleanup() {
  kill "${API_PID:-}" "${WEB_PID:-}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

.venv/bin/uvicorn apps.api.app.main:app --reload --host 127.0.0.1 --port "${API_PORT:-8000}" &
API_PID=$!
npm --prefix apps/web run dev -- --port "${WEB_PORT:-3000}" &
WEB_PID=$!
wait -n "$API_PID" "$WEB_PID"
