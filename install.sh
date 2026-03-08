#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# install.sh — First-time setup for OpenClaw Email Supervisor
#
# Creates the secrets/ directory, placeholder files for every
# required credential, the load_secrets.sh helper, and the
# run.sh entry-point.  Run once after cloning the repository.
# ─────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SECRETS_DIR="${SCRIPT_DIR}/secrets"
VENV_DIR="${SCRIPT_DIR}/.venv"

# ── colours (no-op if not a tty) ─────────────────────────────
if [ -t 1 ]; then
  GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
else
  GREEN=''; YELLOW=''; RED=''; NC=''
fi

info()  { echo -e "${GREEN}[✓]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
error() { echo -e "${RED}[✗]${NC} $*" >&2; }

# ── 1. Create secrets/ directory (mode 700) ──────────────────
if [ -d "$SECRETS_DIR" ]; then
  warn "secrets/ directory already exists — keeping existing files."
else
  mkdir -p "$SECRETS_DIR"
  chmod 700 "$SECRETS_DIR"
  info "Created secrets/ directory (permissions 700)."
fi

# ── 2. Create placeholder secret files (mode 600) ───────────
declare -A SECRETS=(
  [email_username]="YOUR_EMAIL_USERNAME_HERE"
  [email_password]="YOUR_EMAIL_APP_PASSWORD_HERE"
  [telegram_bot_token]="YOUR_TELEGRAM_BOT_TOKEN_HERE"
  [telegram_chat_id]="YOUR_TELEGRAM_CHAT_ID_HERE"
)

for secret_name in "${!SECRETS[@]}"; do
  secret_file="${SECRETS_DIR}/${secret_name}"
  if [ -f "$secret_file" ]; then
    warn "${secret_name} already exists — skipping."
  else
    echo -n "${SECRETS[$secret_name]}" > "$secret_file"
    chmod 600 "$secret_file"
    info "Created secrets/${secret_name} (permissions 600)."
  fi
done

# ── 3. Create virtual environment if missing ─────────────────
if [ ! -d "$VENV_DIR" ]; then
  info "Creating Python virtual environment in .venv/ ..."
  python3 -m venv "$VENV_DIR"
  info "Virtual environment created."
fi

# ── 4. Install dependencies ─────────────────────────────────
info "Installing Python dependencies ..."
"${VENV_DIR}/bin/pip" install --quiet --upgrade pip
"${VENV_DIR}/bin/pip" install --quiet -r "${SCRIPT_DIR}/requirements.txt"
info "Dependencies installed."

# ── 5. Ensure data directories exist ────────────────────────
mkdir -p "${SCRIPT_DIR}/data/logs"
mkdir -p "${SCRIPT_DIR}/data/accounts"
info "Runtime data directories ready."

# ── 6. Done — show instructions ─────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  Installation complete!"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "  Next steps:"
echo ""
echo "  1. Edit each file in secrets/ with your real credentials:"
echo ""
echo "       nano secrets/email_username"
echo "       nano secrets/email_password"
echo "       nano secrets/telegram_bot_token"
echo "       nano secrets/telegram_chat_id"
echo ""
echo "  2. Copy and configure your account:"
echo ""
echo "       cp config/accounts/_template.json config/accounts/my_account.json"
echo "       nano config/accounts/my_account.json"
echo ""
echo "  3. Start the supervisor:"
echo ""
echo "       ./run.sh"
echo ""
echo "═══════════════════════════════════════════════════════════"
