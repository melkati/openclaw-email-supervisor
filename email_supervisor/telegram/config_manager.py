"""Telegram config manager — applies parsed commands to the system.

Receives :class:`ParsedCommand` instances from the command handler and
executes the corresponding operations against the store and orchestrator,
then returns a human-readable response string for Telegram.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from email_supervisor.persistence.store import AccountStore
from email_supervisor.telegram.command_handler import HELP_TEXT, ParsedCommand
from email_supervisor.utils.logging_config import get_logger

if TYPE_CHECKING:
    from email_supervisor.orchestrator import AccountOrchestrator

log = get_logger("config_manager")


class ConfigManager:
    """Execute Telegram commands against the store and orchestrator."""

    def __init__(
        self,
        store: AccountStore,
        orchestrator: Optional["AccountOrchestrator"] = None,
        authorized_chats: Optional[set[int | str]] = None,
    ) -> None:
        self._store = store
        self._orch = orchestrator
        self._authorized = authorized_chats or set()

    def is_authorized(self, chat_id: int | str) -> bool:
        """Check if a chat is authorized to issue commands."""
        if not self._authorized:
            return True  # No auth configured → allow all
        return chat_id in self._authorized or str(chat_id) in {str(c) for c in self._authorized}

    async def execute(self, cmd: ParsedCommand) -> str:
        """Execute a parsed command and return a response message."""
        handler = _HANDLERS.get(cmd.intent)
        if handler is None:
            return "❓ Unknown command. Try /help"
        try:
            return await handler(self, cmd)
        except Exception as exc:
            log.error("Command execution failed: %s", exc, extra={"account": cmd.account_id or ""})
            return f"❌ Error: {exc}"

    # ── command handlers ──────────────────────────────────────

    async def _handle_help(self, _cmd: ParsedCommand) -> str:
        return HELP_TEXT

    async def _handle_list_accounts(self, _cmd: ParsedCommand) -> str:
        if not self._orch:
            return "⚠️ Orchestrator not available"
        accounts = self._orch.list_accounts()
        if not accounts:
            return "No accounts configured."
        lines = ["📧 <b>Accounts</b>\n"]
        for acc in accounts:
            status = "▶️" if acc.get("running") else "⏸"
            lines.append(f"  {status} <b>{acc['id']}</b> — {acc.get('display_name', '')}")
        return "\n".join(lines)

    async def _handle_status(self, cmd: ParsedCommand) -> str:
        aid = cmd.account_id
        if not aid:
            return "Usage: /status <account_id>"
        stats = self._store.get_stats(aid)
        if not stats:
            return f"Account '{aid}' not found."
        return (
            f"📊 <b>{aid}</b>\n"
            f"Processed: {stats.get('total_processed', 0)}\n"
            f"Spam: {stats.get('spam', 0)}\n"
            f"Important: {stats.get('important', 0)}\n"
            f"Uncertain: {stats.get('uncertain', 0)}\n"
            f"AI tokens today: {stats.get('ai_tokens_used_today', 0)}"
        )

    async def _handle_add_whitelist(self, cmd: ParsedCommand) -> str:
        if not cmd.account_id or not cmd.email:
            return "Usage: /whitelist <account_id> <email>"
        self._store.add_to_whitelist(cmd.account_id, {
            "pattern": cmd.email,
            "type": "exact",
            "source": "manual",
        })
        self._reload_pipeline(cmd.account_id)
        return f"✅ Added {cmd.email} to {cmd.account_id} whitelist"

    async def _handle_remove_whitelist(self, cmd: ParsedCommand) -> str:
        if not cmd.account_id or not cmd.email:
            return "Usage: /unwhitelist <account_id> <email>"
        found = self._store.remove_from_whitelist(cmd.account_id, cmd.email)
        if found:
            return f"✅ Removed {cmd.email} from {cmd.account_id} whitelist"
        return f"⚠️ {cmd.email} not found in {cmd.account_id} whitelist"

    async def _handle_add_blacklist(self, cmd: ParsedCommand) -> str:
        if not cmd.account_id or not cmd.email:
            return "Usage: /blacklist <account_id> <email>"
        self._store.add_to_blacklist(cmd.account_id, {
            "pattern": cmd.email,
            "type": "exact",
            "source": "manual",
        })
        self._reload_pipeline(cmd.account_id)
        return f"✅ Added {cmd.email} to {cmd.account_id} blacklist"

    async def _handle_remove_blacklist(self, cmd: ParsedCommand) -> str:
        if not cmd.account_id or not cmd.email:
            return "Usage: /unblacklist <account_id> <email>"
        found = self._store.remove_from_blacklist(cmd.account_id, cmd.email)
        if found:
            return f"✅ Removed {cmd.email} from {cmd.account_id} blacklist"
        return f"⚠️ {cmd.email} not found in {cmd.account_id} blacklist"

    async def _handle_list_rules(self, cmd: ParsedCommand) -> str:
        if not cmd.account_id:
            return "Usage: /rules <account_id>"
        rules = self._store.get_rules(cmd.account_id)
        if not rules:
            return f"No rules for {cmd.account_id}."
        lines = [f"📋 <b>Rules for {cmd.account_id}</b>\n"]
        for r in rules[:20]:  # limit output
            status = "✅" if r.get("enabled") else "❌"
            shadow = " 👻" if r.get("shadow") else ""
            stats = r.get("stats", {})
            lines.append(
                f"  {status}{shadow} <code>{r.get('id', '?')}</code> — "
                f"{r.get('name', '?')} (matches: {stats.get('matches', 0)})"
            )
        return "\n".join(lines)

    async def _handle_toggle_rule(self, cmd: ParsedCommand) -> str:
        if not cmd.account_id or not cmd.rule_id:
            return "Usage: /rule <account_id> <rule_id> on|off"
        rules = self._store.get_rules(cmd.account_id)
        for rule in rules:
            if rule.get("id") == cmd.rule_id:
                rule["enabled"] = cmd.value == "on"
                self._store.upsert_rule(cmd.account_id, rule)
                self._reload_pipeline(cmd.account_id)
                state = "enabled" if rule["enabled"] else "disabled"
                return f"✅ Rule {cmd.rule_id} {state}"
        return f"⚠️ Rule {cmd.rule_id} not found"

    async def _handle_approve_rule(self, cmd: ParsedCommand) -> str:
        if not cmd.account_id or not cmd.rule_id:
            return "Usage: /approve <account_id> <rule_id>"
        rules = self._store.get_rules(cmd.account_id)
        for rule in rules:
            if rule.get("id") == cmd.rule_id and rule.get("shadow"):
                rule["shadow"] = False
                self._store.upsert_rule(cmd.account_id, rule)
                self._reload_pipeline(cmd.account_id)
                return f"✅ Rule {cmd.rule_id} promoted from shadow to active"
        return f"⚠️ Shadow rule {cmd.rule_id} not found"

    async def _handle_set_interval(self, cmd: ParsedCommand) -> str:
        if not cmd.account_id or not cmd.value:
            return "Usage: /interval <account_id> <seconds>"
        try:
            seconds = int(cmd.value)
        except ValueError:
            return "⚠️ Interval must be a number (seconds)"
        if seconds < 10:
            return "⚠️ Minimum interval is 10 seconds"
        # Update the config in the store
        config = self._store.load_config(cmd.account_id)
        config.setdefault("polling", {})["interval_seconds"] = seconds
        self._store.save_config(cmd.account_id, config)
        return f"✅ Interval for {cmd.account_id} set to {seconds}s"

    async def _handle_pause(self, cmd: ParsedCommand) -> str:
        if not cmd.account_id:
            return "Usage: /pause <account_id>"
        if self._orch:
            self._orch.pause_account(cmd.account_id)
        return f"⏸ Account {cmd.account_id} paused"

    async def _handle_resume(self, cmd: ParsedCommand) -> str:
        if not cmd.account_id:
            return "Usage: /resume <account_id>"
        if self._orch:
            self._orch.resume_account(cmd.account_id)
        return f"▶️ Account {cmd.account_id} resumed"

    async def _handle_tokens(self, cmd: ParsedCommand) -> str:
        if not cmd.account_id:
            return "Usage: /tokens <account_id>"
        stats = self._store.get_stats(cmd.account_id)
        used = stats.get("ai_tokens_used_today", 0)
        config = self._store.load_config(cmd.account_id)
        limit = config.get("pipeline", {}).get("ai_max_tokens_per_day", 5000)
        pct = (used / limit * 100) if limit else 0
        bar = "█" * int(pct // 10) + "░" * (10 - int(pct // 10))
        return (
            f"🤖 <b>AI tokens for {cmd.account_id}</b>\n"
            f"[{bar}] {pct:.0f}%\n"
            f"{used} / {limit} tokens used today"
        )

    async def _handle_digest(self, cmd: ParsedCommand) -> str:
        if not cmd.account_id:
            return "Usage: /digest <account_id>"
        # TODO: generate actual digest
        return f"📊 Digest for {cmd.account_id}: coming soon"

    async def _handle_check_now(self, cmd: ParsedCommand) -> str:
        if not cmd.account_id:
            return "Usage: /check <account_id>"
        if self._orch:
            self._orch.trigger_check(cmd.account_id)
        return f"🔍 Manual check triggered for {cmd.account_id}"

    # ── helpers ───────────────────────────────────────────────

    def _reload_pipeline(self, account_id: str) -> None:
        """Tell the orchestrator to hot-reload the pipeline for an account."""
        if self._orch:
            self._orch.reload_pipeline(account_id)


# ── handler registry ──────────────────────────────────────────

_HANDLERS: dict[str, any] = {
    "help": ConfigManager._handle_help,
    "list_accounts": ConfigManager._handle_list_accounts,
    "status": ConfigManager._handle_status,
    "add_whitelist": ConfigManager._handle_add_whitelist,
    "remove_whitelist": ConfigManager._handle_remove_whitelist,
    "add_blacklist": ConfigManager._handle_add_blacklist,
    "remove_blacklist": ConfigManager._handle_remove_blacklist,
    "list_rules": ConfigManager._handle_list_rules,
    "toggle_rule": ConfigManager._handle_toggle_rule,
    "approve_rule": ConfigManager._handle_approve_rule,
    "set_interval": ConfigManager._handle_set_interval,
    "pause": ConfigManager._handle_pause,
    "resume": ConfigManager._handle_resume,
    "tokens": ConfigManager._handle_tokens,
    "digest": ConfigManager._handle_digest,
    "check_now": ConfigManager._handle_check_now,
}
