"""Rule action execution.

When a rule matches, its ``action`` dict describes what to do.  This
module converts action dicts into concrete operations against the IMAP
server, the pipeline result, and the notification system.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from email_supervisor.models.classification import (
    ClassificationResult,
    ClassifiedBy,
    Label,
)


@dataclass(slots=True)
class ActionPlan:
    """Collected actions to execute after a rule matches.

    The pipeline reads this to decide what to do with the email.
    """

    classification: Optional[Label] = None
    move_to: Optional[str] = None
    flag: Optional[str] = None
    notify: bool = True
    skip_ai: bool = False
    force_ai: bool = False
    tags: list[str] = field(default_factory=list)
    rule_id: str = ""

    # Whether this action terminates the pipeline (has a classification)
    @property
    def is_terminal(self) -> bool:
        return self.classification is not None

    def to_classification_result(self) -> Optional[ClassificationResult]:
        """Convert to a ClassificationResult if a classification was set."""
        if self.classification is None:
            return None
        return ClassificationResult(
            label=self.classification,
            classified_by=ClassifiedBy.RULE_ENGINE,
            confidence=1.0,
            reason=f"Matched rule {self.rule_id}",
            rule_id=self.rule_id,
            tags=self.tags,
        )


_LABEL_MAP: dict[str, Label] = {
    "spam": Label.SPAM,
    "important": Label.IMPORTANT,
    "neutral": Label.NEUTRAL,
    "suspicious": Label.SUSPICIOUS,
    "trusted": Label.TRUSTED,
}


def build_action_plan(action_dict: dict, rule_id: str) -> ActionPlan:
    """Parse an ``action`` dict from a rule and return an ActionPlan."""
    classification = None
    raw_label = action_dict.get("classification")
    if raw_label and raw_label in _LABEL_MAP:
        classification = _LABEL_MAP[raw_label]

    return ActionPlan(
        classification=classification,
        move_to=action_dict.get("move_to"),
        flag=action_dict.get("flag"),
        notify=action_dict.get("notify", True),
        skip_ai=action_dict.get("skip_ai", False),
        force_ai=action_dict.get("force_ai", False),
        tags=action_dict.get("tags", []),
        rule_id=rule_id,
    )
