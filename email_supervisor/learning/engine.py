"""Learning engine — orchestrates the auto-learning sub-modules.

Runs after each batch of classified emails:
1. Updates the FrequencyAnalyzer
2. Recalculates SenderScorer
3. Applies auto-blacklist / auto-whitelist
4. Proposes new rules via RuleGenerator
5. Evaluates shadow rules for promotion
6. Persists learning state
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from email_supervisor.learning.frequency_analyzer import FrequencyAnalyzer
from email_supervisor.learning.rule_generator import RuleGenerator
from email_supervisor.learning.sender_scorer import SenderScorer
from email_supervisor.models.account_config import LearningConfig
from email_supervisor.models.classification import ClassificationResult
from email_supervisor.models.email_message import EmailMessage
from email_supervisor.persistence.store import AccountStore
from email_supervisor.utils.logging_config import get_logger

if TYPE_CHECKING:
    from email_supervisor.notifications.dispatcher import NotificationDispatcher

log = get_logger("learning_engine")


class LearningEngine:
    """Orchestrates statistical learning from email classification results."""

    def __init__(
        self,
        store: AccountStore,
        account_id: str,
        config: LearningConfig,
        notifier: Optional["NotificationDispatcher"] = None,
    ) -> None:
        self._store = store
        self._account_id = account_id
        self._config = config
        self._notifier = notifier

        # Load persisted state
        state = store.get_learning_state(account_id)
        self._analyzer = FrequencyAnalyzer(state)
        self._scorer = SenderScorer(store, account_id)
        self._rule_gen = RuleGenerator(
            store, account_id, min_occurrences=config.auto_rules_min_occurrences
        )

    def ingest(
        self,
        results: list[tuple[EmailMessage, ClassificationResult]],
    ) -> None:
        """Process a batch of classification results.

        This is the main entry point called by the pipeline after
        each batch.
        """
        if not results:
            return

        # 1. Update frequency counters
        self._analyzer.update(results)

        # 2. Update sender scores
        self._scorer.update(results)

        # 3. Auto-blacklist / auto-whitelist
        self._apply_auto_lists()

        # 4. Propose new rules
        proposals = self._rule_gen.analyze_and_propose(self._analyzer)
        for proposal in proposals:
            self._store.upsert_rule(self._account_id, proposal)
            log.info(
                "Proposed shadow rule: %s", proposal.get("name"),
                extra={"account": self._account_id},
            )
            # Notify user
            if self._notifier:
                import asyncio
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(
                        self._notifier.notify_learning_event(
                            self._account_id,
                            "New rule proposed",
                            f"{proposal.get('name')} (shadow mode — "
                            f"will auto-activate if accurate)",
                        )
                    )
                except RuntimeError:
                    pass  # No event loop running

        # 5. Evaluate shadow rules
        promoted = self._rule_gen.evaluate_shadow_rules()
        for rule in promoted:
            if self._notifier:
                import asyncio
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(
                        self._notifier.notify_learning_event(
                            self._account_id,
                            "Rule promoted to active",
                            f"{rule.get('name')} passed shadow evaluation",
                        )
                    )
                except RuntimeError:
                    pass

        # 6. Persist learning state
        self._persist()

    def _apply_auto_lists(self) -> None:
        """Apply auto-blacklist and auto-whitelist from sender scores."""
        # Auto-blacklist
        bl_candidates = self._scorer.get_auto_blacklist_candidates(
            threshold=self._config.auto_blacklist_threshold
        )
        for sender, data in bl_candidates:
            self._store.add_to_blacklist(self._account_id, {
                "pattern": sender,
                "type": "exact",
                "source": "auto_learned",
                "confidence": abs(data.get("score", 0)),
                "reason": f"Auto-blacklisted: score={data.get('score', 0):.2f}, "
                          f"seen={data.get('total_seen', 0)}",
            })
            self._scorer.mark_auto_action(sender, "blacklisted")
            log.info(
                "Auto-blacklisted %s (score=%.2f)",
                sender, data.get("score", 0),
                extra={"account": self._account_id},
            )

        # Auto-whitelist
        wl_candidates = self._scorer.get_auto_whitelist_candidates(
            threshold=self._config.auto_whitelist_threshold
        )
        for sender, data in wl_candidates:
            self._store.add_to_whitelist(self._account_id, {
                "pattern": sender,
                "type": "exact",
                "source": "auto_learned",
                "confidence": data.get("score", 0),
                "reason": f"Auto-whitelisted: score={data.get('score', 0):.2f}, "
                          f"seen={data.get('total_seen', 0)}",
            })
            self._scorer.mark_auto_action(sender, "whitelisted")
            log.info(
                "Auto-whitelisted %s (score=%.2f)",
                sender, data.get("score", 0),
                extra={"account": self._account_id},
            )

    def _persist(self) -> None:
        """Save the learning state to the store."""
        state = {
            "pattern_buffer": self._analyzer.to_dict(),
            "pending_rules": [],  # shadow rules are in rules.json
            "last_analysis": datetime.now(timezone.utc).isoformat(),
        }
        self._store.save_learning_state(self._account_id, state)
