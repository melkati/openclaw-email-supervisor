---
name: email-supervisor
description: "Supervise multiple IMAP email accounts, filter spam with a rule-based engine, classify with AI only when necessary, auto-learn patterns, and configure everything via Telegram."
metadata:
  openclaw:
    emoji: "📧"
    requires:
      bins:
        - python3
      env:
        - EMAIL_SUPERVISOR_CONFIG_PATH
    primaryEnv: EMAIL_SUPERVISOR_CONFIG_PATH
    install:
      - id: uv
        kind: uv
        args:
          - pip
          - install
          - "-r"
          - requirements.txt
        label: Install Python dependencies via uv
---

# Email Supervisor

A multi-account IMAP email supervision skill. Filters spam using a dynamic rule
engine first, and only escalates to AI classification when strictly necessary.
Learns automatically from traffic patterns and is fully configurable via Telegram.

## Quick reference

| Subcommand | Description |
| --- | --- |
| `python -m email_supervisor run` | Start the supervisor (foreground) |
| `python -m email_supervisor run --daemon` | Start as background daemon |
| `python -m email_supervisor status [ACCOUNT]` | Show account status |
| `python -m email_supervisor check-now [ACCOUNT]` | Force immediate check |
| `python -m email_supervisor add-whitelist ACCOUNT EMAIL` | Whitelist a sender |
| `python -m email_supervisor add-blacklist ACCOUNT EMAIL` | Blacklist a sender |
| `python -m email_supervisor remove-whitelist ACCOUNT EMAIL` | Remove from whitelist |
| `python -m email_supervisor remove-blacklist ACCOUNT EMAIL` | Remove from blacklist |
| `python -m email_supervisor list-rules ACCOUNT` | List rules with stats |
| `python -m email_supervisor toggle-rule ACCOUNT RULE_ID` | Enable/disable a rule |
| `python -m email_supervisor approve-rule ACCOUNT RULE_ID` | Approve a pending rule |
| `python -m email_supervisor tail-log [N]` | Show last N log entries |

## Environment variables

| Variable | Required | Description |
| --- | --- | --- |
| `EMAIL_SUPERVISOR_CONFIG_PATH` | Yes | Path to the `config/` directory |
| `EMAIL_USERNAME` | Yes | IMAP email address (loaded from `secrets/email_username`) |
| `EMAIL_PASSWORD` | Yes | IMAP app password (loaded from `secrets/email_password`) |
| `TELEGRAM_BOT_TOKEN` | No | Telegram bot token (loaded from `secrets/telegram_bot_token`) |
| `TELEGRAM_CHAT_ID` | No | Telegram chat ID (loaded from `secrets/telegram_chat_id`) |

### Secrets management

Credentials are stored in individual files inside `secrets/` (git-ignored,
permissions `700`). The `run.sh` script loads them automatically via
`load_secrets.sh` — you never need to export variables manually.

Secret reference schemes supported in config files:

| Scheme | Example | Description |
| --- | --- | --- |
| `env:` | `env:EMAIL_PASSWORD` | Read from environment variable |
| `file:` | `file:secrets/email_password` | Read from a local file |
| `vault:` | `vault:email_pass` | *(future)* OS keyring / secret manager |

## How it works

1. The supervisor polls (or IDLEs on) each configured IMAP account.
2. New emails pass through a **4-stage pipeline** before AI is ever considered:
   - **Dedup filter** — skip already-processed messages.
   - **Whitelist / Blacklist filter** — instant classify known senders.
   - **Rule engine filter** — evaluate dynamic rules on metadata only.
   - **AI filter** — last resort, with aggressive token trimming.
3. A **learning engine** runs after each batch to detect patterns and propose
   new rules automatically.
4. Notifications and configuration happen through Telegram.
