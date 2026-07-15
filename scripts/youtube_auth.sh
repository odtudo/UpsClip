#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$ROOT_DIR/.venv"
PYTHON_BIN="$VENV_DIR/bin/python"
AUTH_SCRIPT="$ROOT_DIR/scripts/youtube_auth.py"
OAUTH_REQUIREMENTS="$ROOT_DIR/scripts/requirements-youtube-auth.txt"
CLIENT_SECRET="$ROOT_DIR/data/credentials/client_secret.json"
TOKEN_FILE="$ROOT_DIR/data/credentials/token.json"
CREDENTIALS_DIR="$ROOT_DIR/data/credentials"
TARGET_USER=""
TARGET_GROUP=""

fail() {
  echo "YouTube authorization error: $*" >&2
  exit 1
}

if [[ ! -f "$CLIENT_SECRET" ]]; then
  fail "missing $CLIENT_SECRET. Download a Google OAuth Desktop app JSON and place it there."
fi

if [[ $(id -u) -eq 0 ]] && id kali >/dev/null 2>&1; then
  TARGET_USER="kali"
  TARGET_GROUP="$(id -gn kali)"
  echo "Running the graphical OAuth flow as user kali."
fi

run_as_target() {
  if [[ -n "$TARGET_USER" ]]; then
    local target_home
    target_home="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
    runuser -u "$TARGET_USER" -- env \
      HOME="$target_home" \
      DISPLAY="${DISPLAY:-}" \
      WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-}" \
      XAUTHORITY="${XAUTHORITY:-$target_home/.Xauthority}" \
      DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-}" \
      BROWSER="${BROWSER:-}" \
      "$@"
  else
    "$@"
  fi
}

mkdir -p "$CREDENTIALS_DIR"
if ! run_as_target test -r "$CLIENT_SECRET"; then
  fail "$CLIENT_SECRET is not readable by ${TARGET_USER:-the current user}."
fi
if ! run_as_target test -w "$CREDENTIALS_DIR"; then
  if [[ -n "$TARGET_USER" ]]; then
    chown "$TARGET_USER:$TARGET_GROUP" "$CREDENTIALS_DIR" || \
      fail "could not make $CREDENTIALS_DIR writable by $TARGET_USER."
    chmod u+rwx,go-rwx "$CREDENTIALS_DIR"
  else
    fail "$CREDENTIALS_DIR is not writable. Fix its ownership for $(id -un)."
  fi
fi

if [[ ! -x "$PYTHON_BIN" ]]; then
  SYSTEM_PYTHON="$(command -v python3 || true)"
  [[ -n "$SYSTEM_PYTHON" ]] || fail "python3 is not installed. Install python3 and python3-venv."
  echo "Creating native virtual environment at $VENV_DIR..."
  if ! run_as_target "$SYSTEM_PYTHON" -m venv "$VENV_DIR"; then
    if [[ -n "$TARGET_USER" ]]; then
      "$SYSTEM_PYTHON" -m venv "$VENV_DIR" || \
        fail "could not create .venv. Install python3-venv and ensure $ROOT_DIR is writable."
      chown -R "$TARGET_USER:$TARGET_GROUP" "$VENV_DIR"
    else
      fail "could not create .venv. Install python3-venv and ensure $ROOT_DIR is writable."
    fi
  fi
  echo "Installing only the native YouTube OAuth dependencies..."
  run_as_target "$VENV_DIR/bin/pip" install -r "$OAUTH_REQUIREMENTS" || \
    fail "OAuth dependencies could not be installed. Retry: $VENV_DIR/bin/pip install -r $OAUTH_REQUIREMENTS"
fi

run_as_target "$PYTHON_BIN" "$AUTH_SCRIPT" || \
  fail "OAuth did not complete. No credentials were displayed or modified by this wrapper."

if [[ ! -s "$TOKEN_FILE" ]]; then
  fail "authorization returned without generating $TOKEN_FILE."
fi
chmod 600 "$TOKEN_FILE"
if ! run_as_target test -r "$TOKEN_FILE"; then
  fail "the generated token is not readable by ${TARGET_USER:-the current user}."
fi

echo "OAuth token generated successfully at data/credentials/token.json."
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  if docker compose ps --status running api 2>/dev/null | grep -q api; then
    echo "Restarting the API so it sees the authorized token..."
    docker compose restart api || \
      fail "the API restart failed. Run this command manually: docker compose restart api"
  else
    echo "API is not running. After starting it, use: docker compose restart api"
  fi
else
  echo "Docker Compose is unavailable. After starting the stack, use: docker compose restart api"
fi
