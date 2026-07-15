#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

for directory in credentials downloads work rendered subtitles thumbnails logs models profiles smoke_tests analysis; do
  mkdir -p "data/$directory"
done
chmod u+rwX data data/*
./scripts/download_face_model.sh

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example."
else
  echo "Kept existing .env (no values were overwritten)."
fi

if command -v docker >/dev/null && docker compose version >/dev/null 2>&1; then
  echo "Docker Compose is available. Run: docker compose up --build"
elif [[ -x .venv/bin/python ]]; then
  PATH="$ROOT_DIR/.venv/bin:$PATH" .venv/bin/python scripts/check_real_setup.py
else
  echo "Docker Compose is unavailable and .venv is missing. Follow Native Linux/Kali setup in README.md." >&2
  exit 1
fi
