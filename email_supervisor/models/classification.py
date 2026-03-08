"""Classification labels and result container."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Label(str, Enum):
    """Possible classification labels for an email."""

    SPAM = "spam"
    IMPORTANT = "important"
    NEUTRAL = "neutral"
    SUSPICIOUS = "suspicious"
    UNCERTAIN = "uncertain"
    TRUSTED = "trusted"
    ERROR = "error"


class ClassifiedBy(str, Enum):
    """Which pipeline stage produced the classification."""

    DEDUP = "dedup"
    WHITELIST = "whitelist"
    BLACKLIST = "blacklist"
    RULE_ENGINE = "rule_engine"
    AI = "ai"
    FALLBACK = "fallback"


@dataclass(slots=True)
class ClassificationResult:
    """The outcome of running an email through the pipeline."""

    label: Label
    classified_by: ClassifiedBy
    confidence: float = 1.0
    reason: str = ""
    rule_id: Optional[str] = None
    ai_tokens_used: int = 0
    tags: list[str] = field(default_factory=list)

    # ── helpers ───────────────────────────────────────────────
    @property
    def is_spam(self) -> bool:
        return self.label == Label.SPAM

    @property
    def is_important(self) -> bool:
        return self.label in (Label.IMPORTANT, Label.TRUSTED)

    @property
    def needs_notification(self) -> bool:
        return self.label in (Label.IMPORTANT, Label.SUSPICIOUS, Label.UNCERTAIN)
