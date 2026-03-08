"""WhatsApp notifier — stub for future implementation."""

from __future__ import annotations

from email_supervisor.models.classification import ClassificationResult
from email_supervisor.models.email_message import EmailMessage
from email_supervisor.utils.logging_config import get_logger

log = get_logger("whatsapp_notifier")


class WhatsAppNotifier:
    """Placeholder for WhatsApp Business API integration.

    Not implemented in v1.  All methods log a warning and return.
    """

    async def notify_email(
        self,
        account_id: str,
        msg: EmailMessage,
        result: ClassificationResult,
    ) -> None:
        log.warning("WhatsApp notifier not implemented yet")

    async def send_message(self, text: str) -> None:
        log.warning("WhatsApp notifier not implemented yet")
