"""Sender scorer — per-sender reputation scoring.

Computes a score s ∈ [-1, +1] for each sender:

    s = (n_important - n_spam) / n_total * (1 - exp(-n_total / τ))

where τ is a smoothing factor (default 5) to avoid making decisions
based on too few data points.

Triggers:
- Auto-blacklist when s < -0.8 and n_total >= threshold
- Auto-whitelist when s > 0.8 and n_total >= threshold
"""

from __future__ import annotations

import math
from typing import Optional

from email_supervisor.models.classification import ClassificationResult, Label
from email_supervisor.models.email_message import EmailMessage
from email_supervisor.persistence.store import AccountStore
from email_supervisor.utils.constants import (
    SENDER_SCORE_BLACKLIST_THRESHOLD,
    SENDER_SCORE_TAU,
    SENDER_SCORE_WHITELIST_THRESHOLD,
)
from email_supervisor.utils.logging_config import get_logger

log = get_logger("sender_scorer")


class SenderScorer:
    """Track and update per-sender reputation scores."""

    def __init__(
        self,
        store: AccountStore,
        account_id: str,
        tau: float = SENDER_SCORE_TAU,
    ) -> None:
        self._store = store
        self._account_id = account_id
        self._tau = tau

    def update(
        self, results: list[tuple[EmailMessage, ClassificationResult]]
    ) -> None:
        """Update scores from a classified batch."""
        for msg, result in results:
            sender = msg.sender.lower()
            if not sender:
                continue

            current = self._store.get_sender_score(self._account_id, sender)
            if current is None:
                current = {
                    "total_seen": 0,
                    "spam_count": 0,
                    "important_count": 0,
                    "neutral_count": 0,
                    "score": 0.0,
                    "last_seen": "",
                    "auto_action": None,
                }

            current["total_seen"] = current.get("total_seen", 0) + 1
            if result.label == Label.SPAM:
                current["spam_count"] = current.get("spam_count", 0) + 1
            elif result.label in (Label.IMPORTANT, Label.TRUSTED):
                current["important_count"] = current.get("important_count", 0) + 1
            else:
                current["neutral_count"] = current.get("neutral_count", 0) + 1

            current["score"] = self._compute_score(
                current.get("important_count", 0),
                current.get("spam_count", 0),
                current.get("total_seen", 1),
            )
            from datetime import datetime, timezone
            current["last_seen"] = datetime.now(timezone.utc).isoformat()

            self._store.upsert_sender_score(self._account_id, sender, current)

    def _compute_score(
        self, n_important: int, n_spam: int, n_total: int
    ) -> float:
        """Compute the sender score with smoothing."""
        if n_total == 0:
            return 0.0
        raw = (n_important - n_spam) / n_total
        smoothing = 1.0 - math.exp(-n_total / self._tau)
        return raw * smoothing

    def get_auto_blacklist_candidates(
        self, threshold: int = 3
    ) -> list[tuple[str, dict]]:
        """Return senders eligible for auto-blacklisting."""
        scores = self._store.get_sender_scores(self._account_id)
        candidates = []
        for sender, data in scores.items():
            if (
                data.get("score", 0) < SENDER_SCORE_BLACKLIST_THRESHOLD
                and data.get("total_seen", 0) >= threshold
                and data.get("auto_action") != "blacklisted"
            ):
                candidates.append((sender, data))
        return candidates

    def get_auto_whitelist_candidates(
        self, threshold: int = 5
    ) -> list[tuple[str, dict]]:
        """Return senders eligible for auto-whitelisting."""
        scores = self._store.get_sender_scores(self._account_id)
        candidates = []
        for sender, data in scores.items():
            if (
                data.get("score", 0) > SENDER_SCORE_WHITELIST_THRESHOLD
                and data.get("total_seen", 0) >= threshold
                and data.get("auto_action") != "whitelisted"
            ):
                candidates.append((sender, data))
        return candidates

    def mark_auto_action(self, sender: str, action: str) -> None:
        """Record that an auto-action was applied (blacklisted/whitelisted)."""
        current = self._store.get_sender_score(self._account_id, sender)
        if current:
            current["auto_action"] = action
            self._store.upsert_sender_score(self._account_id, sender, current)
