"""Main entry point and CLI for Email Supervisor.

Usage::

    python -m email_supervisor run              # foreground
    python -m email_supervisor run --daemon      # background (systemd)
    python -m email_supervisor status
    python -m email_supervisor check-now [account]
    python -m email_supervisor add-whitelist <account> <entry>
    python -m email_supervisor remove-whitelist <account> <entry>
    python -m email_supervisor add-blacklist <account> <entry>
    python -m email_supervisor remove-blacklist <account> <entry>
    python -m email_supervisor list-rules <account>
    python -m email_supervisor toggle-rule <account> <rule-id>
    python -m email_supervisor approve-rule <account> <rule-id>
    python -m email_supervisor tail-log [--lines N]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import sys
from pathlib import Path

from email_supervisor.utils.logging_config import setup_logging, get_logger

log = get_logger("main")


def _resolve_paths() -> tuple[Path, Path]:
    """Return (config_root, data_root) based on env or defaults."""
    config_env = os.environ.get("EMAIL_SUPERVISOR_CONFIG_PATH")
    if config_env:
        config_root = Path(config_env)
    else:
        config_root = Path.home() / ".openclaw" / "skills" / "email-supervisor" / "config"

    data_root = config_root.parent / "data"
    return config_root, data_root


def _load_global_config(config_root: Path) -> dict:
    """Load global_config.json from the config root."""
    path = config_root / "global_config.json"
    if not path.exists():
        log.warning("No global_config.json found at %s — using defaults", path)
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


# ── Subcommand handlers ──────────────────────────────────────


async def _cmd_run(args: argparse.Namespace) -> None:
    """Start the orchestrator loop."""
    from email_supervisor.orchestrator import AccountOrchestrator

    config_root, data_root = _resolve_paths()
    global_cfg = _load_global_config(config_root)

    setup_logging(
        log_dir=str(data_root / "logs"),
        level=global_cfg.get("log_level", "INFO"),
    )

    telegram_chats = global_cfg.get("telegram", {}).get("authorized_chat_ids", [])

    orchestrator = AccountOrchestrator(
        config_root=config_root,
        data_root=data_root,
        telegram_chat_ids=telegram_chats,
    )

    # Wire up signal handling for graceful shutdown
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    def _signal_handler() -> None:
        log.info("Received shutdown signal")
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass

    try:
        await orchestrator.start_all()
        log.info("Email Supervisor running — press Ctrl+C to stop")

        # Optionally start Telegram config bot
        bot_token = global_cfg.get("telegram", {}).get("bot_token")
        if bot_token:
            await _start_telegram_bot(bot_token, telegram_chats, orchestrator)

        # On Windows, fall back to polling for Ctrl+C
        if sys.platform == "win32":
            try:
                while not shutdown_event.is_set():
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                pass
        else:
            await shutdown_event.wait()
    finally:
        await orchestrator.stop_all()
        log.info("Shutdown complete")


async def _start_telegram_bot(
    bot_token: str,
    chat_ids: list,
    orchestrator,
) -> None:
    """Start Telegram config bot in the background."""
    try:
        from email_supervisor.telegram.config_manager import ConfigManager

        mgr = ConfigManager(orchestrator=orchestrator, store=orchestrator._store)
        # The actual bot polling would be started here.
        # For v1, we log readiness; full webhook/polling setup comes with
        # python-telegram-bot integration in a future iteration.
        log.info("Telegram ConfigManager ready (bot token configured)")
    except ImportError:
        log.warning("python-telegram-bot not installed — Telegram config disabled")


def _cmd_status(args: argparse.Namespace) -> None:
    """Print account status summary."""
    config_root, data_root = _resolve_paths()
    from email_supervisor.persistence.json_store import JSONStore

    store = JSONStore(data_root=data_root, config_root=config_root)

    accounts_dir = config_root / "accounts"
    if not accounts_dir.exists():
        print("No accounts configured.")
        return

    for path in sorted(accounts_dir.glob("*.json")):
        if path.name.startswith("_"):
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))
        aid = raw.get("account_id", path.stem)
        enabled = raw.get("enabled", True)
        stats = store.load_stats(aid)
        processed = stats.get("total_processed", 0) if stats else 0
        spam = stats.get("total_spam", 0) if stats else 0
        print(f"  {aid:<25s} enabled={enabled}  processed={processed}  spam={spam}")


def _cmd_check_now(args: argparse.Namespace) -> None:
    """Trigger immediate check (placeholder — needs running orchestrator)."""
    print(
        f"check-now: To trigger an immediate check, send '/check {args.account or ''}' "
        "via Telegram or use the running process."
    )


def _cmd_list_modify(args: argparse.Namespace) -> None:
    """Add/remove whitelist/blacklist entries."""
    config_root, data_root = _resolve_paths()
    from email_supervisor.persistence.json_store import JSONStore

    store = JSONStore(data_root=data_root, config_root=config_root)
    action = args.subcommand  # e.g. "add-whitelist"
    parts = action.split("-")
    verb = parts[0]  # add | remove
    list_name = parts[1]  # whitelist | blacklist

    if list_name == "whitelist":
        entries = store.load_whitelist(args.account)
    else:
        entries = store.load_blacklist(args.account)

    if verb == "add":
        if args.entry not in entries:
            entries.append(args.entry)
            print(f"Added '{args.entry}' to {list_name} for {args.account}")
        else:
            print(f"'{args.entry}' already in {list_name}")
    else:
        if args.entry in entries:
            entries.remove(args.entry)
            print(f"Removed '{args.entry}' from {list_name} for {args.account}")
        else:
            print(f"'{args.entry}' not found in {list_name}")

    if list_name == "whitelist":
        store.save_whitelist(args.account, entries)
    else:
        store.save_blacklist(args.account, entries)


def _cmd_list_rules(args: argparse.Namespace) -> None:
    """Print rules for an account."""
    config_root, data_root = _resolve_paths()
    from email_supervisor.persistence.json_store import JSONStore

    store = JSONStore(data_root=data_root, config_root=config_root)
    rules = store.load_rules(args.account)

    if not rules:
        print(f"No rules for {args.account}")
        return

    for r in rules:
        status = "ON" if r.get("enabled", True) else "OFF"
        shadow = " [SHADOW]" if r.get("shadow", False) else ""
        name = r.get("name", r.get("id", "?"))
        print(f"  [{status}]{shadow} {name}")


def _cmd_toggle_rule(args: argparse.Namespace) -> None:
    """Toggle a rule on/off."""
    config_root, data_root = _resolve_paths()
    from email_supervisor.persistence.json_store import JSONStore

    store = JSONStore(data_root=data_root, config_root=config_root)
    rules = store.load_rules(args.account)

    for r in rules:
        if r.get("id") == args.rule_id or r.get("name") == args.rule_id:
            r["enabled"] = not r.get("enabled", True)
            store.save_rules(args.account, rules)
            state = "enabled" if r["enabled"] else "disabled"
            print(f"Rule '{args.rule_id}' is now {state}")
            return

    print(f"Rule '{args.rule_id}' not found")


def _cmd_approve_rule(args: argparse.Namespace) -> None:
    """Promote a shadow rule to active."""
    config_root, data_root = _resolve_paths()
    from email_supervisor.persistence.json_store import JSONStore

    store = JSONStore(data_root=data_root, config_root=config_root)
    rules = store.load_rules(args.account)

    for r in rules:
        if r.get("id") == args.rule_id or r.get("name") == args.rule_id:
            if r.get("shadow"):
                r["shadow"] = False
                store.save_rules(args.account, rules)
                print(f"Rule '{args.rule_id}' promoted from shadow to active")
            else:
                print(f"Rule '{args.rule_id}' is already active")
            return

    print(f"Rule '{args.rule_id}' not found")


def _cmd_tail_log(args: argparse.Namespace) -> None:
    """Print the last N lines of the log file."""
    _, data_root = _resolve_paths()
    log_path = data_root / "logs" / "email_supervisor.log"
    if not log_path.exists():
        print("No log file found.")
        return

    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    n = args.lines or 50
    for line in lines[-n:]:
        print(line)


# ── CLI parser ────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="email-supervisor",
        description="OpenClaw Email Supervisor — multi-account IMAP mail supervision",
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    # run
    p_run = sub.add_parser("run", help="Start the supervisor")
    p_run.add_argument("--daemon", action="store_true", help="Daemonize (systemd)")

    # status
    sub.add_parser("status", help="Show account statuses")

    # check-now
    p_check = sub.add_parser("check-now", help="Trigger immediate check")
    p_check.add_argument("account", nargs="?", help="Account ID (all if omitted)")

    # whitelist / blacklist commands
    for list_name in ("whitelist", "blacklist"):
        for verb in ("add", "remove"):
            name = f"{verb}-{list_name}"
            p = sub.add_parser(name, help=f"{verb.title()} {list_name} entry")
            p.add_argument("account", help="Account ID")
            p.add_argument("entry", help="Email address, domain, or regex")

    # list-rules
    p_lr = sub.add_parser("list-rules", help="List rules for an account")
    p_lr.add_argument("account", help="Account ID")

    # toggle-rule
    p_tr = sub.add_parser("toggle-rule", help="Toggle rule on/off")
    p_tr.add_argument("account", help="Account ID")
    p_tr.add_argument("rule_id", help="Rule ID or name")

    # approve-rule
    p_ar = sub.add_parser("approve-rule", help="Promote shadow rule to active")
    p_ar.add_argument("account", help="Account ID")
    p_ar.add_argument("rule_id", help="Rule ID or name")

    # tail-log
    p_tl = sub.add_parser("tail-log", help="Print recent log lines")
    p_tl.add_argument("--lines", "-n", type=int, default=50, help="Number of lines")

    return parser


_SYNC_COMMANDS = {
    "status": _cmd_status,
    "check-now": _cmd_check_now,
    "list-rules": _cmd_list_rules,
    "toggle-rule": _cmd_toggle_rule,
    "approve-rule": _cmd_approve_rule,
    "tail-log": _cmd_tail_log,
    "add-whitelist": _cmd_list_modify,
    "remove-whitelist": _cmd_list_modify,
    "add-blacklist": _cmd_list_modify,
    "remove-blacklist": _cmd_list_modify,
}


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.subcommand == "run":
        asyncio.run(_cmd_run(args))
    elif args.subcommand in _SYNC_COMMANDS:
        _SYNC_COMMANDS[args.subcommand](args)
    else:
        parser.print_help()
