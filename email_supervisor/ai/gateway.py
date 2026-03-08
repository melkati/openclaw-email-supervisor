"""AI gateway — manages LLM invocations with budget tracking.

The gateway:
1. Checks the daily token budget before calling the LLM.
2. Uses :class:`TokenOptimizer` to build the smallest possible prompt.
3. Calls the LLM (via ``aiohttp`` POST to a configurable endpoint).
4. Parses the structured JSON response.
5. Updates the budget counter.

In v1 the gateway calls an OpenAI-compatible ``/chat/completions``
endpoint.  The actual provider (OpenAI, local Ollama, etc.) is
controlled by the ``AI_BASE_URL`` / ``AI_API_KEY`` env vars.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Optional

from email_supervisor.ai.prompt_templates import (
    SYSTEM_PROMPT,
    build_classification_prompt,
)
from email_supervisor.ai.token_optimizer import TokenOptimizer
from email_supervisor.models.email_message import EmailMessage
from email_supervisor.persistence.store import AccountStore
from email_supervisor.utils.logging_config import get_logger

log = get_logger("ai_gateway")

try:
    import aiohttp
except ImportError:
    aiohttp = None  # type: ignore[assignment]


class AIGateway:
    """LLM classification with budget tracking and token optimization."""

    def __init__(
        self,
        store: AccountStore,
        max_tokens_per_day: int = 5000,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: str = "gpt-4o-mini",
    ) -> None:
        self._store = store
        self._max_tokens = max_tokens_per_day
        self._base_url = base_url or os.environ.get(
            "AI_BASE_URL", "https://api.openai.com/v1"
        )
        self._api_key = api_key or os.environ.get("AI_API_KEY", "")
        self._model = model
        self._optimizer = TokenOptimizer()

        # In-memory budget cache per account (flushed to store)
        self._budgets: dict[str, dict] = {}

    # ── budget management ─────────────────────────────────────

    def _get_budget(self, account_id: str) -> dict:
        """Load or create today's budget for an account."""
        if account_id in self._budgets:
            budget = self._budgets[account_id]
            # Reset if it's a new day
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            if budget.get("date") != today:
                budget = {"date": today, "tokens_used": 0}
                self._budgets[account_id] = budget
            return budget

        stats = self._store.get_stats(account_id)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if stats.get("ai_tokens_date") == today:
            budget = {
                "date": today,
                "tokens_used": stats.get("ai_tokens_used_today", 0),
            }
        else:
            budget = {"date": today, "tokens_used": 0}

        self._budgets[account_id] = budget
        return budget

    def _consume_tokens(self, account_id: str, tokens: int) -> None:
        """Record token consumption."""
        budget = self._get_budget(account_id)
        budget["tokens_used"] = budget.get("tokens_used", 0) + tokens

        # Persist
        stats = self._store.get_stats(account_id)
        stats["ai_tokens_used_today"] = budget["tokens_used"]
        stats["ai_tokens_date"] = budget["date"]
        self._store.save_stats(account_id, stats)

    def is_available(self, account_id: str) -> bool:
        """Check if AI can be used (budget not exhausted, key present)."""
        if not self._api_key:
            return False
        budget = self._get_budget(account_id)
        return budget.get("tokens_used", 0) < self._max_tokens

    def tokens_remaining(self, account_id: str) -> int:
        """Return the number of tokens remaining today."""
        budget = self._get_budget(account_id)
        return max(0, self._max_tokens - budget.get("tokens_used", 0))

    # ── classification ────────────────────────────────────────

    async def classify(
        self, msg: EmailMessage, extra_tags: list[str] | None = None
    ) -> Optional[dict[str, Any]]:
        """Classify an email via the LLM.

        Returns a dict with ``label``, ``confidence``, ``reason``,
        ``tokens_used``, or None on failure.
        """
        if aiohttp is None:
            log.error("aiohttp not installed — AI classification unavailable")
            return None

        # Prepare optimized prompt
        flags, snippet, meta_conf = self._optimizer.prepare(msg)
        if extra_tags:
            flags.extend(extra_tags)

        prompt = build_classification_prompt(
            sender=msg.sender,
            subject=msg.subject,
            flags=flags,
            snippet=snippet,
        )

        # Call LLM
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 100,
            "temperature": 0.1,
        }

        headers = {
            "Content-Type": "application/json",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self._base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        log.error("LLM API error %d: %s", resp.status, body[:200])
                        return None
                    data = await resp.json()
        except Exception as exc:
            log.error("LLM request failed: %s", exc)
            return None

        # Parse response
        try:
            usage = data.get("usage", {})
            tokens_used = usage.get("total_tokens", 0)
            content = data["choices"][0]["message"]["content"].strip()

            # Try to parse JSON from the response
            # Handle potential markdown code fences
            if content.startswith("```"):
                content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            result = json.loads(content)
            result["tokens_used"] = tokens_used

            # Record consumption
            # We need the account_id — get it from the message context
            # (The caller should handle this, but we track here too)
            self._consume_tokens("_global", tokens_used)

            return result

        except (json.JSONDecodeError, KeyError, IndexError) as exc:
            log.warning("Failed to parse LLM response: %s — raw: %s", exc, data)
            return None

    async def classify_for_account(
        self,
        account_id: str,
        msg: EmailMessage,
        extra_tags: list[str] | None = None,
    ) -> Optional[dict[str, Any]]:
        """Classify with per-account budget tracking."""
        if not self.is_available(account_id):
            return None

        result = await self.classify(msg, extra_tags)
        if result:
            self._consume_tokens(account_id, result.get("tokens_used", 0))
        return result
