#!/usr/bin/env bash
# dev.sh — Start backend + frontend dev servers together
# Usage:
#   ./dev.sh          start both servers
#   ./dev.sh restart  restart both servers
#   ./dev.sh logs     tail both log files
#   Ctrl+C            stop everything
#
# Logs are written to: logs/backend.log and logs/frontend.log
# Each run is separated by a timestamped header in the log file.

set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
LOG_DIR="$ROOT_DIR/logs"

# Colors
RESET='\033[0m'
BOLD='\033[1m'
BLUE='\033[1;34m'
GREEN='\033[1;32m'
YELLOW='\033[1;33m'
RED='\033[1;31m'
CYAN='\033[1;36m'

BACKEND_PID=""
FRONTEND_PID=""
BACKEND_LOG="$LOG_DIR/backend.log"
FRONTEND_LOG="$LOG_DIR/frontend.log"

log() { echo -e "${BOLD}[dev]${RESET} $*"; }

init_logs() {
  mkdir -p "$LOG_DIR"
  local ts
  ts=$(date '+%Y-%m-%d %H:%M:%S')
  printf '\n\n━━━ Session started: %s ━━━\n\n' "$ts" | tee -a "$BACKEND_LOG" >> "$FRONTEND_LOG"
}

# Write to terminal (coloured) AND to log file (plain)
prefix_output() {
  local label="$1" color="$2" logfile="$3"
  while IFS= read -r line; do
    echo -e "${color}[$label]${RESET} $line"
    printf '[%s] %s\n' "$(date '+%H:%M:%S')" "$line" >> "$logfile"
  done
}

free_port() {
  local port="$1"
  local pids waited=0
  pids=$(ss -tlnp sport = :"$port" 2>/dev/null \
    | awk 'NR>1 {match($0, /pid=([0-9]+)/, a); if (a[1]) print a[1]}' \
    | sort -u)
  if [ -n "$pids" ]; then
    log "${YELLOW}Port $port in use (PID $pids) — killing...${RESET}"
    echo "$pids" | xargs kill -9 2>/dev/null || true
    while ss -tlnp sport = :"$port" 2>/dev/null | grep -q ":$port" && [ $waited -lt 10 ]; do
      sleep 0.5
      waited=$((waited + 1))
    done
  fi
}

start_backend() {
  free_port 8000
  log "${BLUE}Starting backend...${RESET} (log: ${CYAN}logs/backend.log${RESET})"
  if [ ! -f "$BACKEND_DIR/.env" ]; then
    log "${YELLOW}Warning: backend/.env not found. Copy .env.example and fill in values.${RESET}"
  fi
  local uvicorn="uvicorn"
  if [ -f "$BACKEND_DIR/.venv/bin/uvicorn" ]; then
    uvicorn="$BACKEND_DIR/.venv/bin/uvicorn"
  fi
  (cd "$BACKEND_DIR" && "$uvicorn" app.main:app --reload --host 0.0.0.0 --port 8000 2>&1 \
    | prefix_output "backend" "$BLUE" "$BACKEND_LOG") &
  BACKEND_PID=$!
}

start_frontend() {
  free_port 5173
  log "${GREEN}Starting frontend...${RESET} (log: ${CYAN}logs/frontend.log${RESET})"
  (cd "$FRONTEND_DIR" && npm run dev -- --port 5173 2>&1 \
    | prefix_output "frontend" "$GREEN" "$FRONTEND_LOG") &
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
  printf '\n── Restarted: %s ──\n' "$(date '+%Y-%m-%d %H:%M:%S')" \
    | tee -a "$BACKEND_LOG" >> "$FRONTEND_LOG"
  start_backend
  start_frontend
  log "Servers restarted. Backend: ${BLUE}http://localhost:8000${RESET}  Frontend: ${GREEN}http://localhost:5173${RESET}"
}

trap stop_all EXIT INT TERM
trap restart_all SIGUSR1

# --- Sub-commands ---

if [ "${1:-}" = "logs" ]; then
  log "Tailing ${CYAN}logs/backend.log${RESET} and ${CYAN}logs/frontend.log${RESET} — Ctrl+C to stop"
  tail -f "$BACKEND_LOG" "$FRONTEND_LOG" 2>/dev/null \
    || { log "${RED}No log files yet. Start the servers first with ./dev.sh${RESET}"; exit 1; }
  exit 0
fi

if [ "${1:-}" = "restart" ]; then
  SCRIPT_NAME="$(basename "$0")"
  PIDS=$(pgrep -f "$SCRIPT_NAME" | grep -v "$$" || true)
  if [ -n "$PIDS" ]; then
    echo "$PIDS" | xargs kill -USR1
    log "Restart signal sent."
  else
    log "${RED}No running dev.sh found. Starting fresh.${RESET}"
    init_logs
    start_backend
    start_frontend
  fi
  exit 0
fi

# --- Fresh start ---
init_logs

log "${BOLD}Scenecraft-AI Dev Server${RESET}"
log "Backend  → ${BLUE}http://localhost:8000${RESET}  |  API docs → ${BLUE}http://localhost:8000/docs${RESET}"
log "Frontend → ${GREEN}http://localhost:5173${RESET}"
log "Logs     → ${CYAN}logs/backend.log${RESET}  |  ${CYAN}logs/frontend.log${RESET}"
log "Press ${BOLD}Ctrl+C${RESET} to stop | ${BOLD}./dev.sh restart${RESET} to restart | ${BOLD}./dev.sh logs${RESET} to tail logs\n"

start_backend
start_frontend

# Monitor both — restart whichever dies unexpectedly
while true; do
  sleep 2
  if [ -n "$BACKEND_PID" ] && ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    log "${YELLOW}Backend exited unexpectedly — restarting...${RESET}"
    printf '── Backend crashed and restarted: %s ──\n' "$(date '+%Y-%m-%d %H:%M:%S')" >> "$BACKEND_LOG"
    start_backend
  fi
  if [ -n "$FRONTEND_PID" ] && ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
    log "${YELLOW}Frontend exited unexpectedly — restarting...${RESET}"
    printf '── Frontend crashed and restarted: %s ──\n' "$(date '+%Y-%m-%d %H:%M:%S')" >> "$FRONTEND_LOG"
    start_frontend
  fi
done
