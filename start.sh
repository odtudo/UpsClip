#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
SCRIPT_NAME="$(basename -- "$0")"
API_SERVICE="api"
WEB_SERVICE="web"
WAIT_TIMEOUT=60
COMPOSE=()

info() { printf '%s\n' "$*"; }
error() { printf 'Error: %s\n' "$*" >&2; }
die() { error "$*"; exit 1; }

on_error() {
  local exit_code=$?
  error "Command failed (line ${BASH_LINENO[0]}): ${BASH_COMMAND}"
  exit "$exit_code"
}
trap on_error ERR

usage() {
  cat <<EOF
Usage: ./$SCRIPT_NAME [OPTION]

Start and manage the Docker Compose project.

Options:
  --build    Rebuild images before starting
  --logs     Start if needed, then follow service logs
  --restart  Restart existing services and start any missing services
  --status   Show container state and HTTP health checks
  --stop     Stop and remove project containers and networks
  --clean    Same as --stop; persistent data and credentials are preserved
  --help     Show this help

With no option, existing images are reused and services start in the background.
EOF
}

check_project_root() {
  [[ -f "$ROOT_DIR/docker-compose.yml" ]] || die "docker-compose.yml was not found beside $SCRIPT_NAME. Keep the script in the project root."
  [[ -d "$ROOT_DIR/apps/api" && -d "$ROOT_DIR/apps/web" ]] || die "This does not look like the expected project root: $ROOT_DIR"
  cd "$ROOT_DIR"
}

check_docker() {
  command -v docker >/dev/null 2>&1 || die "Docker is not installed. Install Docker Engine for Kali/Debian and try again."

  if docker compose version >/dev/null 2>&1; then
    COMPOSE=(docker compose)
  elif command -v docker-compose >/dev/null 2>&1 && docker-compose version >/dev/null 2>&1; then
    COMPOSE=(docker-compose)
    info "Warning: using legacy docker-compose because the Docker Compose plugin is unavailable."
  else
    die "Docker Compose is unavailable. Install the Docker Compose plugin (docker-compose-plugin)."
  fi

  if ! docker info >/dev/null 2>&1; then
    if [[ $EUID -eq 0 ]]; then
      die "Cannot access the Docker daemon. Start it with: systemctl start docker"
    fi
    die "Cannot access the Docker daemon. Start Docker, then grant access with: sudo usermod -aG docker $USER (log out and back in afterward)."
  fi
}

ensure_environment() {
  if [[ ! -f .env ]]; then
    [[ -f .env.example ]] || die ".env is missing and .env.example is unavailable."
    cp .env.example .env
    info "Created .env from .env.example."
  fi

  local directory
  for directory in credentials downloads work rendered subtitles thumbnails logs models profiles smoke_tests analysis; do
    mkdir -p "data/$directory"
  done
  chmod u+rwX data data/*
}

env_value() {
  local key=$1 default_value=$2 value
  value="$(sed -n "s/^[[:space:]]*${key}[[:space:]]*=[[:space:]]*//p" .env | tail -n 1)"
  value="${value%$'\r'}"
  value="${value%\"}"; value="${value#\"}"
  value="${value%\'}"; value="${value#\'}"
  printf '%s' "${value:-$default_value}"
}

show_service_logs() {
  local service=$1
  error "Last logs from the $service service:"
  "${COMPOSE[@]}" logs --tail=80 "$service" >&2 || true
}

wait_for_url() {
  local name=$1 url=$2 service=$3 deadline=$((SECONDS + WAIT_TIMEOUT))
  info "Waiting for $name at $url (up to ${WAIT_TIMEOUT}s)..."
  while (( SECONDS < deadline )); do
    if curl --fail --silent --show-error --max-time 3 "$url" >/dev/null 2>&1; then
      info "$name is responding."
      return 0
    fi
    sleep 2
  done
  error "$name did not respond within ${WAIT_TIMEOUT} seconds: $url"
  show_service_logs "$service"
  return 1
}

print_success() {
  local api_port=$1 web_port=$2
  cat <<EOF

Project started successfully

Web:
http://localhost:$web_port

API:
http://localhost:$api_port

Setup status:
http://localhost:$api_port/setup/status

Useful commands:
./start.sh --logs
./start.sh --status
./start.sh --stop
EOF
}

start_project() {
  local build=$1 api_port web_port
  command -v curl >/dev/null 2>&1 || die "curl is required for health checks. Install it with: sudo apt install curl"
  api_port="$(env_value API_PORT 8000)"
  web_port="$(env_value WEB_PORT 3000)"

  if [[ "$build" == true ]]; then
    info "Building and starting services in the background..."
    "${COMPOSE[@]}" up -d --build
  else
    info "Starting services in the background (reusing existing images)..."
    "${COMPOSE[@]}" up -d
  fi

  wait_for_url "API" "http://localhost:$api_port/health" "$API_SERVICE"
  wait_for_url "frontend" "http://localhost:$web_port" "$WEB_SERVICE"
  if ! curl --fail --silent --show-error --max-time 5 "http://localhost:$api_port/setup/status" >/dev/null 2>&1; then
    info "Warning: optional setup status endpoint is not responding."
  fi
  print_success "$api_port" "$web_port"
}

show_status() {
  local api_port web_port failed=0
  api_port="$(env_value API_PORT 8000)"
  web_port="$(env_value WEB_PORT 3000)"
  "${COMPOSE[@]}" ps
  info ""
  if curl --fail --silent --show-error --max-time 5 "http://localhost:$api_port/health" >/dev/null; then
    info "API health: OK (http://localhost:$api_port/health)"
  else
    error "API health: FAILED (http://localhost:$api_port/health)"
    failed=1
  fi
  if curl --fail --silent --show-error --max-time 5 "http://localhost:$web_port" >/dev/null; then
    info "Web health: OK (http://localhost:$web_port)"
  else
    error "Web health: FAILED (http://localhost:$web_port)"
    failed=1
  fi
  if curl --fail --silent --show-error --max-time 5 "http://localhost:$api_port/setup/status" >/dev/null; then
    info "Setup status: OK (http://localhost:$api_port/setup/status)"
  else
    info "Setup status: unavailable (optional)"
  fi
  return "$failed"
}

main() {
  local action="${1:-start}"
  [[ $# -le 1 ]] || { usage >&2; die "Only one option may be used at a time."; }
  case "$action" in
    start|--build|--logs|--restart|--status|--stop|--clean|--help|-h) ;;
    *) usage >&2; die "Unknown option: $action" ;;
  esac
  if [[ "$action" == --help || "$action" == -h ]]; then usage; return; fi

  check_project_root
  check_docker
  ensure_environment

  case "$action" in
    start) start_project false ;;
    --build) start_project true ;;
    --logs)
      start_project false
      info "Following logs (press Ctrl+C to stop following; containers will keep running)..."
      "${COMPOSE[@]}" logs --follow
      ;;
    --restart)
      if [[ -n "$("${COMPOSE[@]}" ps -q)" ]]; then
        info "Restarting existing services..."
        "${COMPOSE[@]}" restart
      fi
      start_project false
      ;;
    --status)
      command -v curl >/dev/null 2>&1 || die "curl is required for health checks. Install it with: sudo apt install curl"
      show_status
      ;;
    --stop|--clean)
      info "Stopping project containers and removing only the project network..."
      "${COMPOSE[@]}" down
      info "Project stopped. Persistent files under data/ were preserved."
      ;;
  esac
}

main "$@"
