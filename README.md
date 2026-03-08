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

# Install dependencies
cd email-supervisor
pip install -r requirements.txt
```

## Configuration

1. Copy the account template:
   ```bash
   cp config/accounts/_template.json config/accounts/my_account.json
   ```
2. Edit the new file with your IMAP credentials and preferences.
3. Set the required environment variables (see SKILL.md).
4. Run: `python -m email_supervisor run`

## Project Structure

```
├── SKILL.md                    # OpenClaw skill definition
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
