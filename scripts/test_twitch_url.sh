#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 https://www.twitch.tv/videos/123456789" >&2
  exit 2
fi
URL="$1"
if [[ ! "$URL" =~ ^https://(www\.|m\.)?twitch\.tv/videos/[0-9]+ ]]; then
  echo "Invalid Twitch VOD URL. Expected https://www.twitch.tv/videos/NUMBER" >&2
  exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
if docker compose ps --status running api 2>/dev/null | grep -q api; then
  exec docker compose exec -T api python -c 'import json,sys; from apps.api.app.config import get_settings; from apps.api.app.services.media import inspect_vod; data=inspect_vod(sys.argv[1],get_settings()); print(json.dumps({"id":data.get("id"),"title":data.get("title"),"duration":data.get("duration"),"availability":data.get("availability")},ensure_ascii=False,indent=2))' "$URL"
fi
if [[ -x .venv/bin/python ]]; then
  export PATH="$ROOT_DIR/.venv/bin:$PATH"
  exec .venv/bin/python -c 'import json,sys; from apps.api.app.config import get_settings; from apps.api.app.services.media import inspect_vod; data=inspect_vod(sys.argv[1],get_settings()); print(json.dumps({"id":data.get("id"),"title":data.get("title"),"duration":data.get("duration"),"availability":data.get("availability")},ensure_ascii=False,indent=2))' "$URL"
fi
echo "Start the stack or create .venv first." >&2
exit 1
