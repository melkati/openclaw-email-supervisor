# OpenClaw Email Supervisor

> Multi-account IMAP email supervision with rule-based spam filtering,
> automatic pattern learning, AI-as-last-resort classification, and
> Telegram-based configuration — packaged as an OpenClaw skill.

## Features

- **Multi-account, multi-server** — supervise any number of IMAP accounts independently.
- **Rule-based spam filtering** — dynamic rule engine with a JSON DSL; no AI required for most emails.
- **Automatic learning** — auto-blacklist, auto-whitelist, and auto-generated rules from traffic patterns.
- **AI only when necessary** — 4 pre-AI filter stages; AI receives aggressively trimmed content.
- **Extreme token savings** — 7-level optimization strategy minimizes LLM costs.
- **Telegram integration** — configure accounts, lists, and rules via natural commands.
- **Per-account isolation** — independent configs, rules, lists, and persistent memory per account.
- **OpenClaw native** — installs as a standard OpenClaw skill.

## Requirements

- Python 3.11+
- An IMAP email account (TLS required)
- *(Optional)* A Telegram bot token for notifications and remote configuration
- *(Optional)* An LLM API key for AI classification fallback

## Installation

```bash
# Clone into your OpenClaw skills directory
cd ~/.openclaw/skills
git clone https://github.com/melkati/openclaw-email-supervisor.git email-supervisor
cd email-supervisor

# Run the installer (creates venv, secrets/, dependencies)
chmod +x install.sh load_secrets.sh run.sh
./install.sh
```

## Secrets Management

Credentials are **never stored in config files**. Instead, they live in
individual files inside a `secrets/` directory that is git-ignored and
restricted to your user only.

After running `./install.sh`, edit each file with your real values:

```bash
nano secrets/email_username        # your IMAP email address
nano secrets/email_password        # your IMAP app password (not your login password)
nano secrets/telegram_bot_token    # Telegram bot token from @BotFather
nano secrets/telegram_chat_id      # your Telegram chat ID
```

The startup script `run.sh` loads these files into environment variables
automatically — you never need to `export` anything manually.

> **Security notes:**
> - `secrets/` directory has permissions `700` (owner only).
> - Each secret file has permissions `600`.
> - `secrets/` is in `.gitignore` and will **never** be committed.
> - For Gmail, use an [App Password](https://myaccount.google.com/apppasswords), not your login password.

### Alternative: file: scheme

Instead of environment variables, you can reference secret files directly
in your account config:

```json
{
  "password": "file:secrets/email_password"
}
```

Supported secret reference schemes: `env:VAR_NAME`, `file:/path/to/file`.

## Configuration

1. Copy the account template:
   ```bash
   cp config/accounts/_template.json config/accounts/my_account.json
   ```
2. Edit the new file with your IMAP credentials and preferences.
3. Start the supervisor:
   ```bash
   ./run.sh
   ```

## Project Structure

```
├── install.sh                  # First-time setup script
├── load_secrets.sh             # Reads secrets/ → env vars
├── run.sh                      # Start the supervisor
├── SKILL.md                    # OpenClaw skill definition
├── secrets/                    # Credentials (git-ignored, 700)
│   ├── email_username          # IMAP username
│   ├── email_password          # IMAP app password
│   ├── telegram_bot_token      # Telegram bot token
│   └── telegram_chat_id        # Telegram chat ID
├── email_supervisor/           # Main Python package
│   ├── main.py                 # CLI entry point
│   ├── orchestrator.py         # Multi-account orchestrator
│   ├── pipeline.py             # Email processing pipeline
│   ├── imap_client.py          # Async IMAP client
│   ├── filters/                # Pipeline filter stages
│   ├── rules/                  # Rule engine (JSON DSL)
│   ├── learning/               # Auto-learning engine
│   ├── ai/                     # AI gateway + token optimizer
│   ├── notifications/          # Telegram / WhatsApp dispatch
│   ├── telegram/               # Telegram command handler
│   ├── persistence/            # JSON / SQLite storage
│   ├── models/                 # Data models
│   └── utils/                  # Logging, security, constants
├── config/                     # Configuration files
│   ├── global_config.json
│   └── accounts/               # One JSON per account
└── data/                       # Runtime data (gitignored)
    ├── accounts/               # Per-account persistent state
    └── logs/                   # Rotating JSON logs
```

## License

MIT
