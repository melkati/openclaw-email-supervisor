"""Abstract interface for per-account persistent storage.

Every concrete backend (JSON files, SQLite, …) must implement
:class:`AccountStore`.  The rest of the application depends only on this
interface, making backend swaps transparent.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional


class AccountStore(ABC):
    """Contract for per-account persistent storage."""

    # ── config ────────────────────────────────────────────────
    @abstractmethod
    def load_config(self, account_id: str) -> dict:
        """Return the raw config dict for *account_id*."""

    @abstractmethod
    def save_config(self, account_id: str, data: dict) -> None:
        """Persist the config dict for *account_id*."""

    # ── processed IDs (dedup) ─────────────────────────────────
    @abstractmethod
    def is_processed(self, account_id: str, msg_id: str) -> bool:
        """Return True if *msg_id* was already processed."""

    @abstractmethod
    def save_processed(self, account_id: str, msg_id: str, result: str) -> None:
        """Record *msg_id* as processed with classification *result*."""

    @abstractmethod
    def compact_processed(self, account_id: str, max_entries: int, max_age_s: int) -> int:
        """Remove old/excess entries; return number removed."""

    # ── whitelist ─────────────────────────────────────────────
    @abstractmethod
    def get_whitelist(self, account_id: str) -> list[dict]:
        """Return all whitelist entries."""

    @abstractmethod
    def add_to_whitelist(self, account_id: str, entry: dict) -> None:
        """Append an entry to the whitelist."""

    @abstractmethod
    def remove_from_whitelist(self, account_id: str, pattern: str) -> bool:
        """Remove by pattern; return True if found."""

    @abstractmethod
    def increment_whitelist_hit(self, account_id: str, pattern: str) -> None:
        """Bump hit counter + last_hit timestamp."""

    # ── blacklist ─────────────────────────────────────────────
    @abstractmethod
    def get_blacklist(self, account_id: str) -> list[dict]:
        """Return all blacklist entries."""

    @abstractmethod
    def add_to_blacklist(self, account_id: str, entry: dict) -> None:
        """Append an entry to the blacklist."""

    @abstractmethod
    def remove_from_blacklist(self, account_id: str, pattern: str) -> bool:
        """Remove by pattern; return True if found."""

    @abstractmethod
    def increment_blacklist_hit(self, account_id: str, pattern: str) -> None:
        """Bump hit counter + last_hit timestamp."""

    # ── rules ─────────────────────────────────────────────────
    @abstractmethod
    def get_rules(self, account_id: str) -> list[dict]:
        """Return all rule dicts sorted by priority."""

    @abstractmethod
    def upsert_rule(self, account_id: str, rule: dict) -> None:
        """Create or update a rule (matched by ``rule["id"]``)."""

    @abstractmethod
    def delete_rule(self, account_id: str, rule_id: str) -> bool:
        """Delete by id; return True if found."""

    @abstractmethod
    def increment_rule_match(self, account_id: str, rule_id: str) -> None:
        """Increment the match counter for a rule."""

    # ── sender scores ─────────────────────────────────────────
    @abstractmethod
    def get_sender_scores(self, account_id: str) -> dict[str, dict]:
        """Return all sender score dicts keyed by sender address."""

    @abstractmethod
    def get_sender_score(self, account_id: str, sender: str) -> Optional[dict]:
        """Return score dict for one sender, or None."""

    @abstractmethod
    def upsert_sender_score(self, account_id: str, sender: str, data: dict) -> None:
        """Create or update a sender score entry."""

    # ── learning state ────────────────────────────────────────
    @abstractmethod
    def get_learning_state(self, account_id: str) -> dict:
        """Return the learning engine state dict."""

    @abstractmethod
    def save_learning_state(self, account_id: str, state: dict) -> None:
        """Persist the learning engine state."""

    # ── stats ─────────────────────────────────────────────────
    @abstractmethod
    def get_stats(self, account_id: str) -> dict:
        """Return aggregate statistics."""

    @abstractmethod
    def save_stats(self, account_id: str, stats: dict) -> None:
        """Persist aggregate statistics."""
