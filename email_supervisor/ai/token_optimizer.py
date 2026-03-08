"""Token optimizer — content trimming before AI classification.

Implements levels L4-L6 of the token savings strategy:

- L4: Header-only analysis when metadata is sufficient
- L5: Aggressive body trimming (first N chars)
- L6: Compact prompt templates (~100-200 tokens total)
"""

from __future__ import annotations

from email_supervisor.models.email_message import EmailMessage
from email_supervisor.utils.constants import (
    HIGH_CONFIDENCE,
    LONG_SNIPPET_CHARS,
    MEDIUM_CONFIDENCE,
    SHORT_SNIPPET_CHARS,
)
from email_supervisor.utils.logging_config import get_logger

log = get_logger("token_optimizer")


class TokenOptimizer:
    """Prepare emails for AI classification with minimal token usage."""

    def __init__(
        self,
        short_snippet: int = SHORT_SNIPPET_CHARS,
        long_snippet: int = LONG_SNIPPET_CHARS,
    ) -> None:
        self._short = short_snippet
        self._long = long_snippet

    def compute_metadata_flags(self, msg: EmailMessage) -> list[str]:
        """Derive signal flags from metadata alone (zero tokens, zero body)."""
        flags: list[str] = []

        if msg.reply_to_mismatch:
            flags.append("reply_to_mismatch")
        if msg.spf_result and msg.spf_result != "pass":
            flags.append(f"spf_{msg.spf_result}")
        if msg.dkim_result and msg.dkim_result != "pass":
            flags.append(f"dkim_{msg.dkim_result}")
        if msg.list_unsubscribe:
            flags.append("has_unsubscribe")
        if msg.has_attachments:
            flags.append("has_attachments")
        if msg.size_bytes > 0 and msg.size_bytes < 2048:
            flags.append("tiny_email")
        if msg.hour is not None and (msg.hour < 6 or msg.hour > 23):
            flags.append("off_hours")

        return flags

    def estimate_metadata_confidence(self, flags: list[str]) -> float:
        """Heuristic confidence from metadata flags alone.

        Returns a score 0.0-1.0 indicating how confident we can be
        about the classification *without* looking at the body.
        """
        score = 0.5  # baseline

        # Strong spam signals
        spam_signals = {"reply_to_mismatch", "has_unsubscribe", "off_hours", "tiny_email"}
        spam_count = len(spam_signals & set(flags))
        if spam_count >= 3:
            score = 0.85
        elif spam_count >= 2:
            score = 0.7

        # Authentication failures
        if any(f.startswith("spf_") or f.startswith("dkim_") for f in flags):
            score = min(score + 0.1, 0.95)

        return score

    def prepare_snippet(
        self, msg: EmailMessage, metadata_confidence: float
    ) -> str:
        """Choose snippet length based on metadata confidence.

        - confidence >= HIGH → skip body entirely (return empty)
        - confidence >= MEDIUM → short snippet (500 chars)
        - confidence < MEDIUM → long snippet (1000 chars)
        """
        if metadata_confidence >= HIGH_CONFIDENCE:
            return ""

        body = msg.body or msg.body_snippet or ""
        if not body:
            return ""

        # Prefer plain text, strip HTML tags naively if needed
        if "<html" in body.lower():
            import re
            body = re.sub(r"<[^>]+>", " ", body)
            body = re.sub(r"\s+", " ", body).strip()

        if metadata_confidence >= MEDIUM_CONFIDENCE:
            return body[: self._short]
        else:
            return body[: self._long]

    def prepare(self, msg: EmailMessage) -> tuple[list[str], str, float]:
        """Full preparation: flags + snippet + confidence.

        Returns
        -------
        (flags, snippet, metadata_confidence)
        """
        flags = self.compute_metadata_flags(msg)
        confidence = self.estimate_metadata_confidence(flags)
        snippet = self.prepare_snippet(msg, confidence)
        return flags, snippet, confidence
