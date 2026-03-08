"""Telegram command handler — parses user commands (slash + natural language).

Supported intents and their patterns:

- List accounts:   /accounts | "show accounts"
- Account status:  /status <id> | "how is <id>"
- Add whitelist:   /whitelist <id> <email> | "whitelist <email> for <id>"
- Add blacklist:   /blacklist <id> <email> | "block <email> for <id>"
- List rules:      /rules <id> | "show rules for <id>"
- Toggle rule:     /rule <id> <rule_id> on|off
- Approve rule:    /approve <id> <rule_id>
- Change interval: /interval <id> <seconds>
- Pause account:   /pause <id>
- Resume account:  /resume <id>
- Token budget:    /tokens <id>
- Force digest:    /digest <id>
- Force check:     /check <id>
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass(slots=True)
class ParsedCommand:
    """Result of parsing a user message into a structured command."""

    intent: str
    account_id: Optional[str] = None
    email: Optional[str] = None
    rule_id: Optional[str] = None
    value: Optional[str] = None
    raw: str = ""


# ── slash command patterns ────────────────────────────────────

_SLASH_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("list_accounts", re.compile(r"^/accounts?\s*$", re.I)),
    ("status", re.compile(r"^/status\s+(\S+)", re.I)),
    ("add_whitelist", re.compile(r"^/whitelist\s+(\S+)\s+(\S+@\S+)", re.I)),
    ("remove_whitelist", re.compile(r"^/unwhitelist\s+(\S+)\s+(\S+@\S+)", re.I)),
    ("add_blacklist", re.compile(r"^/blacklist\s+(\S+)\s+(\S+@\S+)", re.I)),
    ("remove_blacklist", re.compile(r"^/unblacklist\s+(\S+)\s+(\S+@\S+)", re.I)),
    ("list_rules", re.compile(r"^/rules\s+(\S+)", re.I)),
    ("toggle_rule", re.compile(r"^/rule\s+(\S+)\s+(\S+)\s+(on|off)", re.I)),
    ("approve_rule", re.compile(r"^/approve\s+(\S+)\s+(\S+)", re.I)),
    ("set_interval", re.compile(r"^/interval\s+(\S+)\s+(\d+)", re.I)),
    ("pause", re.compile(r"^/pause\s+(\S+)", re.I)),
    ("resume", re.compile(r"^/resume\s+(\S+)", re.I)),
    ("tokens", re.compile(r"^/tokens\s+(\S+)", re.I)),
    ("digest", re.compile(r"^/digest\s+(\S+)", re.I)),
    ("check_now", re.compile(r"^/check\s+(\S+)", re.I)),
    ("help", re.compile(r"^/help\s*$", re.I)),
]

# ── natural language patterns ─────────────────────────────────

_NL_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("list_accounts", re.compile(
        r"(show|list|display)\s+(my\s+)?(accounts?|cuentas?)", re.I
    )),
    ("status", re.compile(
        r"(status|state|how\s+is|how.*doing)\s+(\S+)", re.I
    )),
    ("add_whitelist", re.compile(
        r"(add|put|include|whitelist|allow)\s+(\S+@\S+)\s+.*(whitelist|white|allow|trust).*?(\S+)",
        re.I,
    )),
    ("add_whitelist", re.compile(
        r"(whitelist|trust|allow)\s+(\S+@\S+)\s*(for|in|on)?\s*(\S+)?", re.I
    )),
    ("add_blacklist", re.compile(
        r"(block|blacklist|ban|reject)\s+(\S+@\S+)\s*(for|in|on)?\s*(\S+)?", re.I
    )),
    ("list_rules", re.compile(
        r"(show|list|display)\s+(the\s+)?rules?\s*(for|of|in)?\s*(\S+)?", re.I
    )),
    ("pause", re.compile(
        r"(pause|stop|halt|suspend)\s+(\S+)", re.I
    )),
    ("resume", re.compile(
        r"(resume|start|continue|unpause|reactivate)\s+(\S+)", re.I
    )),
    ("tokens", re.compile(
        r"(tokens?|budget|ai\s+usage)\s*(for|of|in)?\s*(\S+)?", re.I
    )),
    ("check_now", re.compile(
        r"(check|scan|fetch|poll)\s+(\S+)\s*(now|immediately)?", re.I
    )),
]


def parse_command(text: str) -> Optional[ParsedCommand]:
    """Parse a user message into a structured command.

    Tries slash commands first, then natural language patterns.
    Returns None if nothing matches.
    """
    text = text.strip()
    if not text:
        return None

    # Try slash commands first
    for intent, pattern in _SLASH_PATTERNS:
        m = pattern.match(text)
        if m:
            return _build_from_slash(intent, m, text)

    # Try natural language
    for intent, pattern in _NL_PATTERNS:
        m = pattern.search(text)
        if m:
            return _build_from_nl(intent, m, text)

    return None


def _build_from_slash(
    intent: str, m: re.Match, raw: str
) -> ParsedCommand:
    """Build a ParsedCommand from a slash command match."""
    groups = m.groups()
    cmd = ParsedCommand(intent=intent, raw=raw)

    if intent in ("status", "pause", "resume", "tokens", "digest", "check_now"):
        cmd.account_id = groups[0] if groups else None

    elif intent in ("add_whitelist", "remove_whitelist", "add_blacklist", "remove_blacklist"):
        cmd.account_id = groups[0] if len(groups) > 0 else None
        cmd.email = groups[1] if len(groups) > 1 else None

    elif intent == "list_rules":
        cmd.account_id = groups[0] if groups else None

    elif intent == "toggle_rule":
        cmd.account_id = groups[0] if len(groups) > 0 else None
        cmd.rule_id = groups[1] if len(groups) > 1 else None
        cmd.value = groups[2] if len(groups) > 2 else None

    elif intent == "approve_rule":
        cmd.account_id = groups[0] if len(groups) > 0 else None
        cmd.rule_id = groups[1] if len(groups) > 1 else None

    elif intent == "set_interval":
        cmd.account_id = groups[0] if len(groups) > 0 else None
        cmd.value = groups[1] if len(groups) > 1 else None

    return cmd


def _build_from_nl(
    intent: str, m: re.Match, raw: str
) -> ParsedCommand:
    """Build a ParsedCommand from a natural-language match."""
    groups = m.groups()
    cmd = ParsedCommand(intent=intent, raw=raw)

    # Extract email address from anywhere in the raw text
    email_match = re.search(r"(\S+@\S+\.\S+)", raw)
    if email_match:
        cmd.email = email_match.group(1).strip("<>")

    # Extract account id heuristic: last non-email word
    # For most intents, the account is in a specific group position
    if intent == "status":
        cmd.account_id = groups[-1] if groups else None
    elif intent in ("add_whitelist", "add_blacklist"):
        cmd.account_id = groups[-1] if groups else None
    elif intent == "list_rules":
        cmd.account_id = groups[-1] if groups else None
    elif intent in ("pause", "resume", "check_now"):
        cmd.account_id = groups[1] if len(groups) > 1 else None
    elif intent == "tokens":
        cmd.account_id = groups[-1] if groups else None

    return cmd


# ── help text ─────────────────────────────────────────────────

HELP_TEXT = """📧 <b>Email Supervisor Commands</b>

<b>Accounts</b>
/accounts — List all accounts
/status &lt;id&gt; — Account status
/pause &lt;id&gt; — Pause monitoring
/resume &lt;id&gt; — Resume monitoring
/check &lt;id&gt; — Force immediate check

<b>Lists</b>
/whitelist &lt;id&gt; &lt;email&gt; — Add to whitelist
/unwhitelist &lt;id&gt; &lt;email&gt; — Remove from whitelist
/blacklist &lt;id&gt; &lt;email&gt; — Add to blacklist
/unblacklist &lt;id&gt; &lt;email&gt; — Remove from blacklist

<b>Rules</b>
/rules &lt;id&gt; — Show rules
/rule &lt;id&gt; &lt;rule_id&gt; on|off — Toggle rule
/approve &lt;id&gt; &lt;rule_id&gt; — Approve pending rule

<b>Other</b>
/interval &lt;id&gt; &lt;seconds&gt; — Change poll interval
/tokens &lt;id&gt; — Show AI token usage
/digest &lt;id&gt; — Send digest now
/help — Show this help"""
