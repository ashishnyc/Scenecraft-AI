#!/usr/bin/env bash
# dev.sh — Start backend + frontend dev servers together
# Usage:
#   ./dev.sh               start both servers
#   ./dev.sh restart       restart both servers
#   ./dev.sh logs          tail today's log files
#   ./dev.sh logs DATE     tail a specific day  e.g. ./dev.sh logs 2026-04-06
#   Ctrl+C                 stop everything
#
# Logs are written to: logs/backend-YYYY-MM-DD.log and logs/frontend-YYYY-MM-DD.log
# A new file is created each day automatically (even if server runs past midnight).

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
STOPPING=false

log() { echo -e "${BOLD}[dev]${RESET} $*"; }

# Return today's log file path for a given service (backend|frontend)
log_file() { echo "$LOG_DIR/$1-$(date '+%Y-%m-%d').log"; }

init_logs() {
  mkdir -p "$LOG_DIR"
  local ts; ts=$(date '+%Y-%m-%d %H:%M:%S')
  printf '\n━━━ Session started: %s ━━━\n\n' "$ts" \
    | tee -a "$(log_file backend)" >> "$(log_file frontend)"
}

# Stream to terminal (coloured) AND to the daily log file (plain text + timestamp).
# The log file path is resolved per-line so midnight rollovers are handled automatically.
prefix_output() {
  local label="$1" color="$2" logname="$3"
  while IFS= read -r line; do
    echo -e "${color}[$label]${RESET} $line"
    printf '[%s] %s\n' "$(date '+%H:%M:%S')" "$line" >> "$(log_file "$logname")"
  done
}

free_port() {
  local port="$1" pids waited=0
  pids=$(ss -tlnp sport = :"$port" 2>/dev/null \
    | awk 'NR>1 {match($0, /pid=([0-9]+)/, a); if (a[1]) print a[1]}' \
    | sort -u)
  if [ -n "$pids" ]; then
    log "${YELLOW}Port $port in use (PID $pids) — killing...${RESET}"
    echo "$pids" | xargs kill -9 2>/dev/null || true
    while ss -tlnp sport = :"$port" 2>/dev/null | grep -q ":$port" && [ $waited -lt 10 ]; do
      sleep 0.5; waited=$((waited + 1))
    done
  fi
}

start_backend() {
  free_port 8000
  log "${BLUE}Starting backend...${RESET} (log: ${CYAN}logs/backend-$(date '+%Y-%m-%d').log${RESET})"
  if [ ! -f "$BACKEND_DIR/.env" ]; then
    log "${YELLOW}Warning: backend/.env not found. Copy .env.example and fill in values.${RESET}"
  fi
  local uvicorn="uvicorn"
  [ -f "$BACKEND_DIR/.venv/bin/uvicorn" ] && uvicorn="$BACKEND_DIR/.venv/bin/uvicorn"
  (cd "$BACKEND_DIR" && "$uvicorn" app.main:app --reload --host 0.0.0.0 --port 8000 2>&1 \
    | prefix_output "backend" "$BLUE" "backend") &
  BACKEND_PID=$!
}

start_frontend() {
  free_port 5173
  log "${GREEN}Starting frontend...${RESET} (log: ${CYAN}logs/frontend-$(date '+%Y-%m-%d').log${RESET})"
  (cd "$FRONTEND_DIR" && npm run dev -- --port 5173 2>&1 \
    | prefix_output "frontend" "$GREEN" "frontend") &
  FRONTEND_PID=$!
}

stop_all() {
  STOPPING=true
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
  printf '── Restarted: %s ──\n' "$(date '+%Y-%m-%d %H:%M:%S')" \
    | tee -a "$(log_file backend)" >> "$(log_file frontend)"
  start_backend
  start_frontend
  log "Servers restarted. Backend: ${BLUE}http://localhost:8000${RESET}  Frontend: ${GREEN}http://localhost:5173${RESET}"
}

trap stop_all EXIT INT TERM
trap restart_all SIGUSR1

# ── Sub-commands ──────────────────────────────────────────────────────────────

if [ "${1:-}" = "logs" ]; then
  DATE="${2:-$(date '+%Y-%m-%d')}"
  B="$LOG_DIR/backend-$DATE.log"
  F="$LOG_DIR/frontend-$DATE.log"
  if [ ! -f "$B" ] && [ ! -f "$F" ]; then
    log "${RED}No log files found for $DATE.${RESET}"
    log "Available dates:"
    ls "$LOG_DIR"/*.log 2>/dev/null \
      | sed 's|.*/||; s/backend-//; s/frontend-//; s/\.log//' \
      | sort -u | sed 's/^/  /'
    exit 1
  fi
  log "Tailing logs for ${BOLD}$DATE${RESET} — Ctrl+C to stop"
  tail -f $B $F 2>/dev/null
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

# ── Fresh start ───────────────────────────────────────────────────────────────
init_logs

log "${BOLD}Scenecraft-AI Dev Server${RESET}"
log "Backend  → ${BLUE}http://localhost:8000${RESET}  |  API docs → ${BLUE}http://localhost:8000/docs${RESET}"
log "Frontend → ${GREEN}http://localhost:5173${RESET}"
log "Logs     → ${CYAN}logs/backend-$(date '+%Y-%m-%d').log${RESET}  |  ${CYAN}logs/frontend-$(date '+%Y-%m-%d').log${RESET}"
log "Commands → ${BOLD}./dev.sh restart${RESET}  |  ${BOLD}./dev.sh logs${RESET}  |  ${BOLD}./dev.sh logs YYYY-MM-DD${RESET}\n"

start_backend
start_frontend

# Monitor both — restart whichever dies unexpectedly
while true; do
  sleep 2
  $STOPPING && break
  if [ -n "$BACKEND_PID" ] && ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    log "${YELLOW}Backend exited unexpectedly — restarting...${RESET}"
    printf '── Backend crashed and restarted: %s ──\n' "$(date '+%Y-%m-%d %H:%M:%S')" >> "$(log_file backend)"
    start_backend
  fi
  if [ -n "$FRONTEND_PID" ] && ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
    log "${YELLOW}Frontend exited unexpectedly — restarting...${RESET}"
    printf '── Frontend crashed and restarted: %s ──\n' "$(date '+%Y-%m-%d %H:%M:%S')" >> "$(log_file frontend)"
    start_frontend
  fi
done
