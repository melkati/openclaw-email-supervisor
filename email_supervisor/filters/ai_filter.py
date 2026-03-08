"""AI classification filter — stage 4 (last resort) of the pipeline.

This filter is invoked **only** when stages 1-3 fail to classify.
It prepares a token-optimized prompt from email metadata + snippet,
sends it to the LLM via the :class:`AIGateway`, and parses the
structured response.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from email_supervisor.models.classification import (
    ClassificationResult,
    ClassifiedBy,
    Label,
)
from email_supervisor.models.email_message import EmailMessage
from email_supervisor.utils.logging_config import get_logger

if TYPE_CHECKING:
    from email_supervisor.ai.gateway import AIGateway

log = get_logger("ai_filter")

_LABEL_MAP: dict[str, Label] = {
    "spam": Label.SPAM,
    "important": Label.IMPORTANT,
    "neutral": Label.NEUTRAL,
    "suspicious": Label.SUSPICIOUS,
}


class AIClassificationFilter:
    """Pipeline stage that classifies via AI as a last resort."""

    def __init__(self, gateway: "AIGateway", account_id: str) -> None:
        self._gateway = gateway
        self._account_id = account_id

    async def classify(
        self, msg: EmailMessage, tags: list[str]
    ) -> Optional[ClassificationResult]:
        """Classify *msg* via the AI gateway.

        Returns None if AI is disabled, budget exhausted, or the LLM
        response is unparseable.
        """
        if not self._gateway.is_available(self._account_id):
            log.info(
                "AI unavailable for %s (budget or config); classifying as uncertain",
                msg.message_id,
                extra={"account": self._account_id, "msg_id": msg.message_id},
            )
            return ClassificationResult(
                label=Label.UNCERTAIN,
                classified_by=ClassifiedBy.FALLBACK,
                confidence=0.0,
                reason="AI unavailable — budget exhausted or disabled",
                tags=tags,
            )

        try:
            ai_result = await self._gateway.classify(msg, tags)
        except Exception as exc:
            log.error(
                "AI classification failed for %s: %s",
                msg.message_id, exc,
                extra={"account": self._account_id, "msg_id": msg.message_id},
            )
            return ClassificationResult(
                label=Label.UNCERTAIN,
                classified_by=ClassifiedBy.FALLBACK,
                confidence=0.0,
                reason=f"AI error: {exc}",
                tags=tags,
            )

        if ai_result is None:
            return None

        label = _LABEL_MAP.get(ai_result.get("label", ""), Label.UNCERTAIN)
        confidence = float(ai_result.get("confidence", 0.5))
        reason = ai_result.get("reason", "")
        tokens = int(ai_result.get("tokens_used", 0))

        log.info(
            "AI classified %s as %s (confidence=%.2f, tokens=%d)",
            msg.message_id, label.value, confidence, tokens,
            extra={
                "account": self._account_id,
                "msg_id": msg.message_id,
                "classification": label.value,
                "classified_by": "ai",
                "ai_tokens_used": tokens,
            },
        )

        return ClassificationResult(
            label=label,
            classified_by=ClassifiedBy.AI,
            confidence=confidence,
            reason=reason,
            ai_tokens_used=tokens,
            tags=tags,
        )
