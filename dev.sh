#!/usr/bin/env bash
# dev.sh — Start backend + frontend dev servers together
# Usage:
#   ./dev.sh          start both servers
#   ./dev.sh restart  restart both servers
#   Ctrl+C            stop everything

set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

# Colors
RESET='\033[0m'
BOLD='\033[1m'
BLUE='\033[1;34m'
GREEN='\033[1;32m'
YELLOW='\033[1;33m'
RED='\033[1;31m'

BACKEND_PID=""
FRONTEND_PID=""

log() { echo -e "${BOLD}[dev]${RESET} $*"; }

prefix_output() {
  local label="$1" color="$2"
  while IFS= read -r line; do
    echo -e "${color}[$label]${RESET} $line"
  done
}

free_port() {
  local port="$1"
  local pids waited=0
  # Use ss — works for both 0.0.0.0 and 127.0.0.1 bindings
  pids=$(ss -tlnp sport = :"$port" 2>/dev/null \
    | awk 'NR>1 {match($0, /pid=([0-9]+)/, a); if (a[1]) print a[1]}' \
    | sort -u)
  if [ -n "$pids" ]; then
    log "${YELLOW}Port $port in use (PID $pids) — killing...${RESET}"
    echo "$pids" | xargs kill -9 2>/dev/null || true
    # Wait until the port is actually free (up to 5s)
    while ss -tlnp sport = :"$port" 2>/dev/null | grep -q ":$port" && [ $waited -lt 10 ]; do
      sleep 0.5
      waited=$((waited + 1))
    done
  fi
}

start_backend() {
  free_port 8000
  log "${BLUE}Starting backend...${RESET}"
  if [ ! -f "$BACKEND_DIR/.env" ]; then
    log "${YELLOW}Warning: backend/.env not found. Copy .env.example and fill in values.${RESET}"
  fi
  # Resolve uvicorn: prefer .venv, fall back to PATH
  local uvicorn="uvicorn"
  if [ -f "$BACKEND_DIR/.venv/bin/uvicorn" ]; then
    uvicorn="$BACKEND_DIR/.venv/bin/uvicorn"
  fi
  (cd "$BACKEND_DIR" && "$uvicorn" app.main:app --reload --host 0.0.0.0 --port 8000 2>&1 \
    | prefix_output "backend" "$BLUE") &
  BACKEND_PID=$!
}

start_frontend() {
  free_port 5173
  log "${GREEN}Starting frontend...${RESET}"
  (cd "$FRONTEND_DIR" && npm run dev -- --port 5173 2>&1 \
    | prefix_output "frontend" "$GREEN") &
  FRONTEND_PID=$!
}

stop_all() {
  log "${RED}Stopping servers...${RESET}"
  [ -n "$BACKEND_PID" ]  && kill "$BACKEND_PID"  2>/dev/null || true
  [ -n "$FRONTEND_PID" ] && kill "$FRONTEND_PID" 2>/dev/null || true
  wait 2>/dev/null || true
  log "All servers stopped."
}

restart_all() {
  log "${YELLOW}Restarting...${RESET}"
  stop_all
  sleep 1
  start_backend
  start_frontend
  log "Servers restarted. Backend: ${BLUE}http://localhost:8000${RESET}  Frontend: ${GREEN}http://localhost:5173${RESET}"
}

trap stop_all EXIT INT TERM
trap restart_all SIGUSR1

if [ "${1:-}" = "restart" ]; then
  SCRIPT_NAME="$(basename "$0")"
  PIDS=$(pgrep -f "$SCRIPT_NAME" | grep -v "$$" || true)
  if [ -n "$PIDS" ]; then
    echo "$PIDS" | xargs kill -USR1
    log "Restart signal sent."
  else
    log "${RED}No running dev.sh found. Starting fresh.${RESET}"
    start_backend
    start_frontend
  fi
  exit 0
fi

# Fresh start
log "${BOLD}Scenecraft-AI Dev Server${RESET}"
log "Backend  → ${BLUE}http://localhost:8000${RESET}  |  API docs → ${BLUE}http://localhost:8000/docs${RESET}"
log "Frontend → ${GREEN}http://localhost:5173${RESET}"
log "Press ${BOLD}Ctrl+C${RESET} to stop, or run ${BOLD}./dev.sh restart${RESET} to restart.\n"

start_backend
start_frontend

# Monitor both processes — restart whichever one dies unexpectedly
while true; do
  sleep 2
  if [ -n "$BACKEND_PID" ] && ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    log "${YELLOW}Backend exited unexpectedly — restarting...${RESET}"
    start_backend
  fi
  if [ -n "$FRONTEND_PID" ] && ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
    log "${YELLOW}Frontend exited unexpectedly — restarting...${RESET}"
    start_frontend
  fi
done
