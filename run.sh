#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# run.sh — Start OpenClaw Email Supervisor
#
# This script:
#   1. Activates the Python virtual environment (.venv/)
#   2. Loads secrets from secrets/ into environment variables
#   3. Launches the email supervisor
#   4. Handles Ctrl+C for clean shutdown
#
# Usage:  ./run.sh              (foreground, default)
#         ./run.sh --daemon     (background / systemd)
# ─────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/.venv"

# ── Colours ──────────────────────────────────────────────────
if [ -t 1 ]; then
  GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'
else
  GREEN=''; RED=''; NC=''
fi

info()  { echo -e "${GREEN}[✓]${NC} $*"; }
error() { echo -e "${RED}[✗]${NC} $*" >&2; }

# ── 1. Verify virtual environment ───────────────────────────
if [ ! -d "$VENV_DIR" ]; then
  error "Virtual environment not found. Run ./install.sh first."
  exit 1
fi

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"
info "Virtual environment activated."

# ── 2. Load secrets ─────────────────────────────────────────
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/load_secrets.sh"
info "Secrets loaded into environment."

# ── 3. Trap Ctrl+C for clean shutdown ───────────────────────
cleanup() {
  echo ""
  info "Shutting down Email Supervisor ..."
  # The Python process handles SIGINT internally, but if it
  # doesn't exit within 5 seconds, force-kill it.
  if [ -n "${PID:-}" ] && kill -0 "$PID" 2>/dev/null; then
    kill -TERM "$PID" 2>/dev/null || true
    wait "$PID" 2>/dev/null || true
  fi
  info "Stopped."
  exit 0
}
trap cleanup SIGINT SIGTERM

# ── 4. Launch the supervisor ────────────────────────────────
info "Starting Email Supervisor ..."
echo ""

if [[ "${1:-}" == "--daemon" ]]; then
  # Background mode — write PID file for systemd / manual stop
  python3 -m email_supervisor run --daemon &
  PID=$!
  echo "$PID" > "${SCRIPT_DIR}/data/supervisor.pid"
  info "Running in background (PID ${PID})."
  info "Stop with:  kill \$(cat data/supervisor.pid)"
  wait "$PID"
else
  # Foreground mode — block until Ctrl+C
  python3 -m email_supervisor run &
  PID=$!
  wait "$PID"
fi
