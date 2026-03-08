"""Rule engine — evaluates rules against emails.

This is the core of the non-AI classification pipeline.  Rules are
evaluated in priority order (lower number = higher priority).  The
first rule whose conditions match **and** whose action sets a
``classification`` terminates the chain.  Rules with only ``tag`` or
``notify`` actions are additive and do not stop evaluation.
"""

from __future__ import annotations

from typing import Optional

from email_supervisor.models.email_message import EmailMessage
from email_supervisor.rules.actions import ActionPlan, build_action_plan
from email_supervisor.rules.conditions import evaluate_group
from email_supervisor.utils.constants import BUILTIN_RULE_PREFIX
from email_supervisor.utils.logging_config import get_logger

log = get_logger("rule_engine")


# ── built-in rules ────────────────────────────────────────────

BUILTIN_RULES: list[dict] = [
    {
        "id": f"{BUILTIN_RULE_PREFIX}reply_to_mismatch",
        "name": "Reply-To differs from sender",
        "enabled": True,
        "priority": 900,
        "source": "builtin",
        "conditions": {
            "operator": "AND",
            "items": [
                {"field": "reply_to_mismatch", "op": "is", "value": True},
            ],
        },
        "action": {
            "classification": "suspicious",
            "tags": ["reply_to_mismatch"],
            "notify": False,
        },
        "stats": {"matches": 0, "false_positives": 0},
    },
    {
        "id": f"{BUILTIN_RULE_PREFIX}no_spf_dkim",
        "name": "Missing SPF and DKIM",
        "enabled": True,
        "priority": 901,
        "source": "builtin",
        "conditions": {
            "operator": "AND",
            "items": [
                {"field": "spf_result", "op": "not_equals", "value": "pass"},
                {"field": "dkim_result", "op": "not_equals", "value": "pass"},
            ],
        },
        "action": {
            "tags": ["no_auth"],
            "notify": False,
        },
        "stats": {"matches": 0, "false_positives": 0},
    },
    {
        "id": f"{BUILTIN_RULE_PREFIX}has_unsubscribe",
        "name": "List-Unsubscribe header present",
        "enabled": True,
        "priority": 902,
        "source": "builtin",
        "conditions": {
            "operator": "AND",
            "items": [
                {"field": "list_unsubscribe", "op": "exists", "value": True},
            ],
        },
        "action": {
            "tags": ["newsletter"],
            "notify": False,
        },
        "stats": {"matches": 0, "false_positives": 0},
    },
]


class RuleEngine:
    """Evaluate a set of rules against an email message.

    Usage::

        engine = RuleEngine(user_rules + BUILTIN_RULES)
        result = engine.evaluate(msg)
    """

    def __init__(self, rules: list[dict]) -> None:
        # Merge built-in rules (don't duplicate by id)
        ids = {r.get("id") for r in rules}
        merged = list(rules)
        for br in BUILTIN_RULES:
            if br["id"] not in ids:
                merged.append(br)

        # Sort by priority (ascending)
        self._rules = sorted(merged, key=lambda r: r.get("priority", 100))

    @property
    def rules(self) -> list[dict]:
        return self._rules

    def evaluate(
        self, msg: EmailMessage
    ) -> tuple[Optional[ActionPlan], list[ActionPlan]]:
        """Run all rules against *msg*.

        Returns
        -------
        (terminal_action, additive_actions)
            *terminal_action* is the first action that sets a classification
            (or None if no rule matched terminally).
            *additive_actions* are all non-terminal actions that matched
            (tags, notifications, etc.).
        """
        additive: list[ActionPlan] = []
        matched_ids: list[str] = []

        for rule in self._rules:
            if not rule.get("enabled", True):
                continue

            conditions = rule.get("conditions")
            if conditions is None:
                continue

            if not evaluate_group(msg, conditions):
                continue

            # Rule matched
            rule_id = rule.get("id", "?")
            matched_ids.append(rule_id)
            plan = build_action_plan(rule.get("action", {}), rule_id)

            if rule.get("shadow", False):
                # Shadow mode — count but don't act
                log.debug(
                    "Shadow rule %s matched for %s",
                    rule_id,
                    msg.message_id,
                    extra={"account": "", "rule_id": rule_id},
                )
                continue

            if plan.is_terminal:
                log.info(
                    "Rule %s classified %s as %s",
                    rule_id,
                    msg.message_id,
                    plan.classification,
                    extra={
                        "msg_id": msg.message_id,
                        "rule_id": rule_id,
                        "classification": str(plan.classification),
                    },
                )
                return plan, additive

            # Non-terminal (additive)
            additive.append(plan)

        return None, additive
