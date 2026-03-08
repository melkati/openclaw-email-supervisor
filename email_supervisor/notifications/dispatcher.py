"""Notification dispatcher — routes notifications to configured channels."""

from __future__ import annotations

from typing import Optional

from email_supervisor.models.classification import ClassificationResult
from email_supervisor.models.email_message import EmailMessage
from email_supervisor.notifications.telegram_notifier import TelegramNotifier
from email_supervisor.notifications.whatsapp_notifier import WhatsAppNotifier
from email_supervisor.utils.logging_config import get_logger

log = get_logger("dispatcher")


class NotificationDispatcher:
    """Route notifications to one or more channels based on config."""

    def __init__(
        self,
        telegram: Optional[TelegramNotifier] = None,
        whatsapp: Optional[WhatsAppNotifier] = None,
        enabled_channels: Optional[list[str]] = None,
    ) -> None:
        self._telegram = telegram
        self._whatsapp = whatsapp
        self._channels = set(enabled_channels or [])

    async def notify_email(
        self,
        account_id: str,
        msg: EmailMessage,
        result: ClassificationResult,
    ) -> None:
        """Send an email alert to all enabled channels."""
        if "telegram" in self._channels and self._telegram:
            await self._telegram.notify_email(account_id, msg, result)
        if "whatsapp" in self._channels and self._whatsapp:
            await self._whatsapp.notify_email(account_id, msg, result)

    async def send_text(self, text: str) -> None:
        """Broadcast raw text to all channels."""
        if "telegram" in self._channels and self._telegram:
            await self._telegram.send_message(text)
        if "whatsapp" in self._channels and self._whatsapp:
            await self._whatsapp.send_message(text)

    async def notify_learning_event(
        self, account_id: str, event: str, detail: str
    ) -> None:
        """Forward a learning event to Telegram."""
        if "telegram" in self._channels and self._telegram:
            await self._telegram.notify_learning_event(account_id, event, detail)

    async def send_digest(self, account_id: str, summary: str) -> None:
        """Send a daily digest."""
        if "telegram" in self._channels and self._telegram:
            await self._telegram.send_digest(account_id, summary)
