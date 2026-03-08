"""Whitelist / blacklist filter — stage 2 of the pipeline.

Instantly classifies emails whose sender (or sender domain) appears in
the per-account whitelist or blacklist.  Supports three match types:

- ``exact``  — full address match (case-insensitive)
- ``domain`` — domain suffix match (e.g. ``@company.com``)
- ``regex``  — regex match against the full From address
"""

from __future__ import annotations

import re
from typing import Optional

from email_supervisor.models.classification import (
    ClassificationResult,
    ClassifiedBy,
    Label,
)
from email_supervisor.models.email_message import EmailMessage
from email_supervisor.persistence.store import AccountStore
from email_supervisor.utils.logging_config import get_logger

log = get_logger("list_filter")


class WhitelistBlacklistFilter:
    """Classify known senders via whitelist / blacklist lookup."""

    def __init__(self, store: AccountStore, account_id: str) -> None:
        self._store = store
        self._account_id = account_id

    # ── public API ────────────────────────────────────────────

    def classify(self, msg: EmailMessage) -> Optional[ClassificationResult]:
        """Return a classification if sender is in a list, else None."""
        # Check whitelist first (higher trust)
        wl_match = self._match_list(
            msg.sender, msg.sender_domain, self._store.get_whitelist(self._account_id)
        )
        if wl_match is not None:
            pattern = wl_match.get("pattern", "")
            self._store.increment_whitelist_hit(self._account_id, pattern)
            log.info(
                "Whitelist match: %s → trusted (pattern: %s)",
                msg.sender, pattern,
                extra={
                    "account": self._account_id,
                    "msg_id": msg.message_id,
                    "classification": "trusted",
                    "classified_by": "whitelist",
                },
            )
            return ClassificationResult(
                label=Label.TRUSTED,
                classified_by=ClassifiedBy.WHITELIST,
                confidence=wl_match.get("confidence", 1.0),
                reason=f"Whitelist match: {pattern}",
            )

        # Check blacklist
        bl_match = self._match_list(
            msg.sender, msg.sender_domain, self._store.get_blacklist(self._account_id)
        )
        if bl_match is not None:
            pattern = bl_match.get("pattern", "")
            self._store.increment_blacklist_hit(self._account_id, pattern)
            log.info(
                "Blacklist match: %s → spam (pattern: %s)",
                msg.sender, pattern,
                extra={
                    "account": self._account_id,
                    "msg_id": msg.message_id,
                    "classification": "spam",
                    "classified_by": "blacklist",
                },
            )
            return ClassificationResult(
                label=Label.SPAM,
                classified_by=ClassifiedBy.BLACKLIST,
                confidence=bl_match.get("confidence", 1.0),
                reason=f"Blacklist match: {pattern}",
            )

        return None

    # ── matching logic ────────────────────────────────────────

    @staticmethod
    def _match_list(
        sender: str, sender_domain: str, entries: list[dict]
    ) -> Optional[dict]:
        """Return the first matching entry or None."""
        sender_lower = sender.lower()
        domain_lower = sender_domain.lower()

        for entry in entries:
            pattern = entry.get("pattern", "")
            match_type = entry.get("type", "exact")

            if match_type == "exact":
                if pattern.lower() == sender_lower:
                    return entry
                # Also match if the pattern is just the email part
                if f"<{pattern.lower()}>" in sender_lower:
                    return entry

            elif match_type == "domain":
                # Pattern like "@company.com" or "company.com"
                domain_pattern = pattern.lstrip("@").lower()
                if domain_lower == domain_pattern:
                    return entry

            elif match_type == "regex":
                try:
                    if re.search(pattern, sender, re.IGNORECASE):
                        return entry
                except re.error:
                    pass

        return None
