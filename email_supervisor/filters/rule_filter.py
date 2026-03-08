"""Rule engine filter — stage 3 of the pipeline.

Wraps the :class:`RuleEngine` as a pipeline stage.  Evaluates all
configured rules (user + built-in) against the email metadata and
returns a classification if a terminal rule matches.
"""

from __future__ import annotations

from typing import Optional

from email_supervisor.models.classification import ClassificationResult
from email_supervisor.models.email_message import EmailMessage
from email_supervisor.persistence.store import AccountStore
from email_supervisor.rules.engine import RuleEngine
from email_supervisor.utils.logging_config import get_logger

log = get_logger("rule_filter")


class RuleEngineFilter:
    """Pipeline stage that evaluates the dynamic rule engine."""

    def __init__(self, store: AccountStore, account_id: str) -> None:
        self._store = store
        self._account_id = account_id
        self._engine: Optional[RuleEngine] = None
        self._reload()

    def _reload(self) -> None:
        """Load (or reload) rules from the store."""
        raw_rules = self._store.get_rules(self._account_id)
        self._engine = RuleEngine(raw_rules)

    def reload(self) -> None:
        """Public hook for hot-reloading rules after a config change."""
        self._reload()

    def classify(
        self, msg: EmailMessage
    ) -> tuple[Optional[ClassificationResult], list[str]]:
        """Evaluate rules against *msg*.

        Returns
        -------
        (result, tags)
            *result* is the classification if a terminal rule matched,
            otherwise ``None``.  *tags* are accumulated from all
            non-terminal (additive) rules that matched.
        """
        assert self._engine is not None
        terminal, additive = self._engine.evaluate(msg)

        # Collect tags from additive rules
        tags: list[str] = []
        for plan in additive:
            tags.extend(plan.tags)
            # Track match in store
            if plan.rule_id:
                self._store.increment_rule_match(self._account_id, plan.rule_id)

        if terminal is not None:
            # Track terminal match
            if terminal.rule_id:
                self._store.increment_rule_match(self._account_id, terminal.rule_id)
            result = terminal.to_classification_result()
            if result:
                result.tags = tags + terminal.tags
            return result, tags

        return None, tags
