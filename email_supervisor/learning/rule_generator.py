"""Rule generator — automatically creates rules from detected patterns.

Analyzes frequency data to find recurring correlations (e.g. domain +
time-of-day + size → always spam) and generates candidate rules in
**shadow mode**.  Shadow rules run in parallel with the real pipeline
but take no action until they accumulate enough accuracy data.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from email_supervisor.learning.frequency_analyzer import FrequencyAnalyzer
from email_supervisor.persistence.store import AccountStore
from email_supervisor.utils.constants import SHADOW_RULE_MIN_ACCURACY
from email_supervisor.utils.logging_config import get_logger

log = get_logger("rule_generator")


class RuleGenerator:
    """Generate and manage auto-learned rules."""

    def __init__(
        self,
        store: AccountStore,
        account_id: str,
        min_occurrences: int = 4,
    ) -> None:
        self._store = store
        self._account_id = account_id
        self._min_occ = min_occurrences

    def analyze_and_propose(
        self, analyzer: FrequencyAnalyzer
    ) -> list[dict]:
        """Propose new rules based on frequency patterns.

        Returns a list of rule dicts ready for shadow evaluation.
        """
        proposals: list[dict] = []

        # Strategy 1: domains with high spam rate
        for domain, count in analyzer.get_top_spam_domains(20):
            if count < self._min_occ:
                continue
            total_for_domain = analyzer.domains.get(domain, count)
            if total_for_domain == 0:
                continue
            spam_ratio = count / total_for_domain
            if spam_ratio >= 0.85:
                rule = self._make_domain_rule(domain, spam_ratio)
                if rule and not self._rule_exists(rule):
                    proposals.append(rule)

        # Strategy 2: subject keywords with high spam correlation
        for keyword, count in analyzer.get_top_spam_keywords(20):
            if count < self._min_occ:
                continue
            total_for_kw = analyzer.subjects.get(keyword, count)
            if total_for_kw == 0:
                continue
            spam_ratio = count / total_for_kw
            if spam_ratio >= 0.90:
                rule = self._make_keyword_rule(keyword, spam_ratio)
                if rule and not self._rule_exists(rule):
                    proposals.append(rule)

        return proposals

    def evaluate_shadow_rules(self) -> list[dict]:
        """Check shadow rules for promotion to active.

        Returns rules that met the accuracy threshold and should be
        promoted (shadow=False).
        """
        rules = self._store.get_rules(self._account_id)
        promoted: list[dict] = []

        for rule in rules:
            if not rule.get("shadow", False):
                continue
            stats = rule.get("stats", {})
            matches = stats.get("matches", 0)
            false_pos = stats.get("false_positives", 0)

            if matches < self._min_occ:
                continue  # not enough data

            total = matches + false_pos
            accuracy = matches / total if total > 0 else 0
            if accuracy >= SHADOW_RULE_MIN_ACCURACY:
                rule["shadow"] = False
                self._store.upsert_rule(self._account_id, rule)
                promoted.append(rule)
                log.info(
                    "Promoted shadow rule %s (accuracy=%.2f, matches=%d)",
                    rule.get("id"), accuracy, matches,
                )

        return promoted

    # ── rule construction helpers ─────────────────────────────

    def _make_domain_rule(self, domain: str, spam_ratio: float) -> dict:
        """Create a shadow rule that matches a spammy domain."""
        return {
            "id": f"auto_domain_{domain.replace('.', '_')}_{uuid.uuid4().hex[:6]}",
            "name": f"Auto: spam from {domain}",
            "enabled": True,
            "priority": 50,
            "source": "auto_learned",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "shadow": True,
            "conditions": {
                "operator": "AND",
                "items": [
                    {"field": "sender_domain", "op": "equals", "value": domain},
                ],
            },
            "action": {
                "classification": "spam",
                "notify": False,
            },
            "stats": {"matches": 0, "false_positives": 0},
            "_meta": {"spam_ratio": round(spam_ratio, 3)},
        }

    def _make_keyword_rule(self, keyword: str, spam_ratio: float) -> dict:
        """Create a shadow rule that matches a spammy subject keyword."""
        return {
            "id": f"auto_kw_{keyword}_{uuid.uuid4().hex[:6]}",
            "name": f"Auto: subject contains '{keyword}'",
            "enabled": True,
            "priority": 55,
            "source": "auto_learned",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "shadow": True,
            "conditions": {
                "operator": "AND",
                "items": [
                    {"field": "subject", "op": "contains", "value": keyword},
                ],
            },
            "action": {
                "classification": "spam",
                "notify": False,
            },
            "stats": {"matches": 0, "false_positives": 0},
            "_meta": {"spam_ratio": round(spam_ratio, 3)},
        }

    def _rule_exists(self, candidate: dict) -> bool:
        """Check if a semantically equivalent rule already exists."""
        existing = self._store.get_rules(self._account_id)
        # Simple dedup: check if same conditions exist
        cand_items = candidate.get("conditions", {}).get("items", [])
        for rule in existing:
            rule_items = rule.get("conditions", {}).get("items", [])
            if cand_items == rule_items:
                return True
        return False
