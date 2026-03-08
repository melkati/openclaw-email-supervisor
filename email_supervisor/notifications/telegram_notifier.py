"""Telegram notifier — sends email alerts via a Telegram bot."""

from __future__ import annotations

import asyncio
from typing import Optional

from email_supervisor.models.classification import ClassificationResult
from email_supervisor.models.email_message import EmailMessage
from email_supervisor.utils.logging_config import get_logger
from email_supervisor.utils.security import resolve_secret

log = get_logger("telegram_notifier")

# Try to import python-telegram-bot
try:
    from telegram import Bot
    from telegram.constants import ParseMode
except ImportError:
    Bot = None  # type: ignore[assignment,misc]
    ParseMode = None  # type: ignore[assignment,misc]


class TelegramNotifier:
    """Send notifications to Telegram chats."""

    def __init__(
        self,
        token_ref: str = "env:TELEGRAM_BOT_TOKEN",
        chat_ids: Optional[list[str | int]] = None,
    ) -> None:
        self._token_ref = token_ref
        self._chat_ids = chat_ids or []
        self._bot: Optional[Bot] = None  # type: ignore[assignment]

    async def _ensure_bot(self) -> bool:
        """Lazily create the Bot instance."""
        if self._bot is not None:
            return True
        if Bot is None:
            log.warning("python-telegram-bot not installed; Telegram disabled")
            return False
        try:
            token = resolve_secret(self._token_ref)
            self._bot = Bot(token=token)
            return True
        except Exception as exc:
            log.error("Failed to initialize Telegram bot: %s", exc)
            return False

    async def send_message(self, text: str) -> None:
        """Send *text* to all configured chat IDs."""
        if not await self._ensure_bot():
            return
        for chat_id in self._chat_ids:
            try:
                await self._bot.send_message(  # type: ignore[union-attr]
                    chat_id=chat_id,
                    text=text,
                    parse_mode=ParseMode.HTML if ParseMode else None,
                )
            except Exception as exc:
                log.error("Telegram send failed (chat %s): %s", chat_id, exc)

    async def notify_email(
        self,
        account_id: str,
        msg: EmailMessage,
        result: ClassificationResult,
    ) -> None:
        """Send an email classification alert."""
        icon = {
            "spam": "🚫",
            "important": "⭐",
            "suspicious": "⚠️",
            "uncertain": "❓",
            "trusted": "✅",
            "neutral": "📧",
        }.get(result.label.value, "📧")

        text = (
            f"{icon} <b>[{account_id}]</b> {result.label.value.upper()}\n"
            f"<b>From:</b> {_escape(msg.sender)}\n"
            f"<b>Subject:</b> {_escape(msg.subject[:100])}\n"
            f"<b>Reason:</b> {_escape(result.reason[:200])}"
        )
        await self.send_message(text)

    async def notify_learning_event(
        self, account_id: str, event: str, detail: str
    ) -> None:
        """Send a learning engine notification (e.g. new rule suggestion)."""
        text = (
            f"🧠 <b>[{account_id}]</b> Learning event\n"
            f"<b>{_escape(event)}</b>\n"
            f"{_escape(detail)}"
        )
        await self.send_message(text)

    async def send_digest(self, account_id: str, summary: str) -> None:
        """Send a daily digest summary."""
        text = f"📊 <b>[{account_id}]</b> Daily Digest\n{_escape(summary)}"
        await self.send_message(text)


def _escape(text: str) -> str:
    """Escape HTML for Telegram."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
