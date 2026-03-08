"""Email processing pipeline.

Orchestrates the 4-stage filter chain for a single account:

1. Dedup filter      → skip already-processed messages
2. List filter       → instant whitelist / blacklist classification
3. Rule filter       → dynamic rule engine on metadata
4. AI filter         → LLM fallback (last resort, token-trimmed)

After classification, the pipeline records the result, feeds the
learning engine, and dispatches notifications.
"""

from __future__ import annotations

import hashlib
import time
from typing import TYPE_CHECKING, Optional

from email_supervisor.filters.dedup_filter import DeduplicationFilter
from email_supervisor.filters.list_filter import WhitelistBlacklistFilter
from email_supervisor.filters.rule_filter import RuleEngineFilter
from email_supervisor.filters.ai_filter import AIClassificationFilter
from email_supervisor.models.account_config import AccountConfig
from email_supervisor.models.classification import (
    ClassificationResult,
    ClassifiedBy,
    Label,
)
from email_supervisor.models.email_message import EmailMessage
from email_supervisor.persistence.store import AccountStore
from email_supervisor.utils.logging_config import get_logger

if TYPE_CHECKING:
    from email_supervisor.ai.gateway import AIGateway
    from email_supervisor.learning.engine import LearningEngine
    from email_supervisor.notifications.dispatcher import NotificationDispatcher

log = get_logger("pipeline")


class EmailPipeline:
    """Four-stage email classification pipeline for one account."""

    def __init__(
        self,
        config: AccountConfig,
        store: AccountStore,
        ai_gateway: "AIGateway",
        learning_engine: Optional["LearningEngine"] = None,
        notifier: Optional["NotificationDispatcher"] = None,
    ) -> None:
        self._config = config
        self._store = store
        self._aid = config.account_id

        # Filter stages
        self._dedup = DeduplicationFilter(store, self._aid)
        self._lists = WhitelistBlacklistFilter(store, self._aid)
        self._rules = RuleEngineFilter(store, self._aid)
        self._ai = AIClassificationFilter(ai_gateway, self._aid)

        # Post-classification
        self._learner = learning_engine
        self._notifier = notifier

    # ── public entry point ────────────────────────────────────

    async def process_batch(
        self, messages: list[EmailMessage]
    ) -> list[tuple[EmailMessage, ClassificationResult]]:
        """Run the full pipeline on a batch of messages.

        Returns a list of (message, result) tuples.
        """
        results: list[tuple[EmailMessage, ClassificationResult]] = []

        # Stage 1: Dedup
        if self._config.pipeline.dedup_enabled:
            messages = self._dedup.filter(messages)

        for msg in messages:
            t0 = time.monotonic()
            result = await self._classify_single(msg)
            latency_ms = int((time.monotonic() - t0) * 1000)

            # Persist
            self._store.save_processed(
                self._aid, msg.message_id, result.label.value
            )

            # Log
            subject_hash = hashlib.sha256(
                msg.subject.encode()
            ).hexdigest()[:12]
            log.info(
                "email_classified",
                extra={
                    "account": self._aid,
                    "msg_id": msg.message_id,
                    "from_addr": msg.sender,
                    "subject_hash": subject_hash,
                    "classification": result.label.value,
                    "classified_by": result.classified_by.value,
                    "rule_id": result.rule_id or "",
                    "ai_tokens_used": result.ai_tokens_used,
                    "latency_ms": latency_ms,
                },
            )

            results.append((msg, result))

        # Post-batch: learning
        if self._learner and self._config.learning.enabled:
            try:
                self._learner.ingest(results)
            except Exception as exc:
                log.error("Learning engine error: %s", exc)

        # Post-batch: notifications
        if self._notifier:
            try:
                await self._notify_batch(results)
            except Exception as exc:
                log.error("Notification error: %s", exc)

        return results

    # ── single-email classification ───────────────────────────

    async def _classify_single(
        self, msg: EmailMessage
    ) -> ClassificationResult:
        """Run stages 2-4 on a single message."""
        accumulated_tags: list[str] = []

        # Stage 2: Whitelist / Blacklist
        if self._config.pipeline.whitelist_enabled or self._config.pipeline.blacklist_enabled:
            list_result = self._lists.classify(msg)
            if list_result is not None:
                return list_result

        # Stage 3: Rule engine
        if self._config.pipeline.rules_enabled:
            rule_result, rule_tags = self._rules.classify(msg)
            accumulated_tags.extend(rule_tags)
            if rule_result is not None:
                return rule_result

        # Stage 4: AI (last resort)
        if self._config.pipeline.ai_enabled:
            ai_result = await self._ai.classify(msg, accumulated_tags)
            if ai_result is not None:
                return ai_result

        # Fallback: nothing matched
        return ClassificationResult(
            label=Label.UNCERTAIN,
            classified_by=ClassifiedBy.FALLBACK,
            confidence=0.0,
            reason="No filter matched",
            tags=accumulated_tags,
        )

    # ── notifications ─────────────────────────────────────────

    async def _notify_batch(
        self, results: list[tuple[EmailMessage, ClassificationResult]]
    ) -> None:
        """Send notifications for emails that warrant them."""
        if not self._notifier:
            return

        notify_on = set(self._config.notifications.notify_on)
        for msg, result in results:
            if result.label.value in notify_on and result.needs_notification:
                await self._notifier.notify_email(
                    account_id=self._aid,
                    msg=msg,
                    result=result,
                )

    # ── hot-reload ────────────────────────────────────────────

    def reload_rules(self) -> None:
        """Reload rules from the store (e.g. after Telegram config change)."""
        self._rules.reload()
