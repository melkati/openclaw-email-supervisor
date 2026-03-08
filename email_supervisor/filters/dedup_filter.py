"""Deduplication filter — stage 1 of the pipeline.

Checks each email's ``message_id`` against the persistent processed-IDs
store and drops anything already seen.  This is the cheapest possible
filter (zero tokens, zero network, pure dict lookup).
"""

from __future__ import annotations

from email_supervisor.models.email_message import EmailMessage
from email_supervisor.persistence.store import AccountStore
from email_supervisor.utils.logging_config import get_logger

log = get_logger("dedup_filter")


class DeduplicationFilter:
    """Remove already-processed emails from a batch."""

    def __init__(self, store: AccountStore, account_id: str) -> None:
        self._store = store
        self._account_id = account_id

    def filter(self, messages: list[EmailMessage]) -> list[EmailMessage]:
        """Return only messages not yet in the processed-IDs store."""
        new: list[EmailMessage] = []
        for msg in messages:
            if self._store.is_processed(self._account_id, msg.message_id):
                log.debug(
                    "Skipping duplicate %s", msg.message_id,
                    extra={"account": self._account_id, "msg_id": msg.message_id},
                )
            else:
                new.append(msg)

        skipped = len(messages) - len(new)
        if skipped:
            log.info(
                "Dedup: %d/%d skipped as already processed",
                skipped, len(messages),
                extra={"account": self._account_id},
            )
        return new

    def filter_uids(self, uids: list[str]) -> list[str]:
        """Cheaper variant that filters raw UID strings."""
        return [
            uid for uid in uids
            if not self._store.is_processed(self._account_id, uid)
        ]
