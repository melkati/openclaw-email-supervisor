"""Frequency analyzer — counts patterns in email metadata.

Maintains sliding-window counters for subject keywords, sender domains,
time-of-day buckets, and size buckets.  Used by the :class:`RuleGenerator`
to detect recurring patterns that can become automatic rules.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Optional

from email_supervisor.models.classification import ClassificationResult, Label
from email_supervisor.models.email_message import EmailMessage
from email_supervisor.utils.logging_config import get_logger

log = get_logger("frequency_analyzer")

# Keywords to ignore when tokenizing subjects
_STOPWORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been",
    "to", "of", "in", "for", "on", "with", "at", "by", "from",
    "and", "or", "not", "no", "but", "if", "this", "that", "it",
    "re", "fwd", "fw",
})

_SIZE_BUCKETS = [
    ("bucket_0_1k", 0, 1024),
    ("bucket_1k_10k", 1024, 10240),
    ("bucket_10k_100k", 10240, 102400),
    ("bucket_100k_plus", 102400, float("inf")),
]


class FrequencyAnalyzer:
    """Track email pattern frequencies in a sliding window."""

    def __init__(self, state: Optional[dict] = None) -> None:
        state = state or {}
        pb = state.get("pattern_buffer", {})
        self.subjects: Counter = Counter(pb.get("subjects", {}))
        self.domains: Counter = Counter(pb.get("domains", {}))
        self.hours: Counter = Counter(pb.get("hours", {}))
        self.sizes: Counter = Counter(pb.get("sizes", {}))
        # Track per-label counters for correlation analysis
        self.spam_subjects: Counter = Counter(pb.get("spam_subjects", {}))
        self.spam_domains: Counter = Counter(pb.get("spam_domains", {}))

    def update(
        self,
        results: list[tuple[EmailMessage, ClassificationResult]],
    ) -> None:
        """Ingest a batch of classified emails."""
        for msg, result in results:
            # Subject keywords
            keywords = self._tokenize_subject(msg.subject)
            self.subjects.update(keywords)

            # Domain
            if msg.sender_domain:
                self.domains[msg.sender_domain] += 1

            # Hour
            if msg.hour is not None:
                self.hours[str(msg.hour)] += 1

            # Size bucket
            for bucket_name, lo, hi in _SIZE_BUCKETS:
                if lo <= msg.size_bytes < hi:
                    self.sizes[bucket_name] += 1
                    break

            # Per-label tracking
            if result.label == Label.SPAM:
                self.spam_subjects.update(keywords)
                if msg.sender_domain:
                    self.spam_domains[msg.sender_domain] += 1

    def to_dict(self) -> dict:
        """Serialize to a dict for persistence."""
        return {
            "subjects": dict(self.subjects),
            "domains": dict(self.domains),
            "hours": dict(self.hours),
            "sizes": dict(self.sizes),
            "spam_subjects": dict(self.spam_subjects),
            "spam_domains": dict(self.spam_domains),
        }

    def get_top_spam_keywords(self, n: int = 10) -> list[tuple[str, int]]:
        """Return the top N subject keywords associated with spam."""
        return self.spam_subjects.most_common(n)

    def get_top_spam_domains(self, n: int = 10) -> list[tuple[str, int]]:
        """Return the top N sender domains associated with spam."""
        return self.spam_domains.most_common(n)

    @staticmethod
    def _tokenize_subject(subject: str) -> list[str]:
        """Extract meaningful keywords from an email subject."""
        words = re.findall(r"[a-zA-Z]{3,}", subject.lower())
        return [w for w in words if w not in _STOPWORDS]
