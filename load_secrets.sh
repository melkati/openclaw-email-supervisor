#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# load_secrets.sh — Read secret files and export as env vars
#
# Usage:  source load_secrets.sh
#
# Each file in secrets/ is mapped to an environment variable:
#   secrets/email_username     → EMAIL_USERNAME
#   secrets/email_password     → EMAIL_PASSWORD
#   secrets/telegram_bot_token → TELEGRAM_BOT_TOKEN
#   secrets/telegram_chat_id   → TELEGRAM_CHAT_ID
#
# Files must contain only the raw secret value (no newlines).
# Trailing newlines are stripped automatically.
# ─────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SECRETS_DIR="${SCRIPT_DIR}/secrets"

# Mapping: filename → environment variable name
declare -A SECRET_MAP=(
  [email_username]="EMAIL_USERNAME"
  [email_password]="EMAIL_PASSWORD"
  [telegram_bot_token]="TELEGRAM_BOT_TOKEN"
  [telegram_chat_id]="TELEGRAM_CHAT_ID"
)

_load_errors=0

for secret_name in "${!SECRET_MAP[@]}"; do
  env_var="${SECRET_MAP[$secret_name]}"
  secret_file="${SECRETS_DIR}/${secret_name}"

  if [ ! -f "$secret_file" ]; then
    echo "[✗] Missing secret file: secrets/${secret_name} (needed for ${env_var})" >&2
    _load_errors=$((_load_errors + 1))
    continue
  fi

  # Read content, strip trailing whitespace/newlines
  value="$(tr -d '\n\r' < "$secret_file")"

  if [ -z "$value" ] || [[ "$value" == YOUR_* ]]; then
    echo "[!] Secret secrets/${secret_name} still has placeholder value — edit it first." >&2
    _load_errors=$((_load_errors + 1))
    continue
  fi

  export "${env_var}=${value}"
done

# Also set the config path if not already set
if [ -z "${EMAIL_SUPERVISOR_CONFIG_PATH:-}" ]; then
  export EMAIL_SUPERVISOR_CONFIG_PATH="${SCRIPT_DIR}/config"
fi

if [ "$_load_errors" -gt 0 ]; then
  echo "" >&2
  echo "[!] ${_load_errors} secret(s) could not be loaded. Edit the files in secrets/ and try again." >&2
fi

unset _load_errors
