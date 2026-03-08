"""Rule data model — mirrors the JSON DSL for the rule engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass(slots=True)
class Condition:
    """A single condition in a rule.

    Example JSON::

        {"field": "sender_domain", "op": "in", "value": ["example.com"]}
    """

    field: str
    op: str
    value: Any


@dataclass(slots=True)
class ConditionGroup:
    """A group of conditions combined with a logical operator.

    Example JSON::

        {
            "operator": "AND",
            "items": [
                {"field": "subject", "op": "contains", "value": "sale"},
                {"operator": "OR", "items": [...]}
            ]
        }
    """

    operator: str  # AND | OR | NOT
    items: list[Condition | ConditionGroup] = field(default_factory=list)


@dataclass(slots=True)
class RuleAction:
    """Actions to execute when a rule matches."""

    classification: Optional[str] = None  # spam | important | neutral | suspicious
    move_to: Optional[str] = None
    flag: Optional[str] = None
    notify: bool = True
    skip_ai: bool = False
    force_ai: bool = False
    tags: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RuleStats:
    """Tracking counters for a rule."""

    matches: int = 0
    false_positives: int = 0

    @property
    def accuracy(self) -> float:
        total = self.matches + self.false_positives
        return (self.matches / total) if total > 0 else 1.0


@dataclass(slots=True)
class Rule:
    """A complete rule definition."""

    id: str
    name: str
    enabled: bool = True
    priority: int = 100  # lower = higher priority
    source: str = "manual"  # manual | auto_learned
    created_at: Optional[datetime] = None
    conditions: Optional[ConditionGroup] = None
    action: RuleAction = field(default_factory=RuleAction)
    stats: RuleStats = field(default_factory=RuleStats)
    shadow: bool = False  # True = evaluate but don't act (learning mode)
