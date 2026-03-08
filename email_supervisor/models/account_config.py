"""Account configuration data model — maps to config/accounts/*.json."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import logging


@dataclass(slots=True)
class IMAPConfig:
    """IMAP server connection settings."""

    host: str = ""
    port: int = 993
    ssl: bool = True
    username: str = ""
    password: str = ""  # e.g. "env:WORK_IMAP_PASS"
    folders: list[str] = field(default_factory=lambda: ["INBOX"])
    idle_supported: bool = True


@dataclass(slots=True)
class PollingConfig:
    """How often and how many emails to fetch."""

    interval_seconds: int = 120
    batch_size: int = 50
    max_age_hours: int = 72


@dataclass(slots=True)
class PipelineConfig:
    """Toggle and tune each pipeline stage."""

    dedup_enabled: bool = True
    whitelist_enabled: bool = True
    blacklist_enabled: bool = True
    rules_enabled: bool = True
    ai_enabled: bool = True
    ai_max_tokens_per_day: int = 5000
    ai_confidence_threshold: float = 0.7


@dataclass(slots=True)
class LearningConfig:
    """Auto-learning engine thresholds."""

    enabled: bool = True
    auto_blacklist_threshold: int = 3
    auto_whitelist_threshold: int = 5
    auto_rules_min_occurrences: int = 4
    learning_window_days: int = 30


@dataclass(slots=True)
class NotificationConfig:
    """Where and when to send notifications."""

    channels: list[str] = field(default_factory=lambda: ["telegram"])
    notify_on: list[str] = field(default_factory=lambda: ["important", "suspicious"])
    digest_enabled: bool = True
    digest_cron: str = "0 9 * * *"


@dataclass(slots=True)
class AccountConfig:
    """Complete configuration for a single email account."""

    account_id: str = ""
    display_name: str = ""
    enabled: bool = True

    imap: IMAPConfig = field(default_factory=IMAPConfig)
    polling: PollingConfig = field(default_factory=PollingConfig)
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)
    learning: LearningConfig = field(default_factory=LearningConfig)
    notifications: NotificationConfig = field(default_factory=NotificationConfig)

    # ── factory ───────────────────────────────────────────────
    @classmethod
    def from_dict(cls, data: dict) -> AccountConfig:
        """Build an AccountConfig from a parsed JSON dict."""
        config = cls(
            account_id=data.get("account_id", ""),
            display_name=data.get("display_name", ""),
            enabled=data.get("enabled", True),
            imap=_build(IMAPConfig, data.get("imap", {})),
            polling=_build(PollingConfig, data.get("polling", {})),
            pipeline=_build(PipelineConfig, data.get("pipeline", {})),
            learning=_build(LearningConfig, data.get("learning", {})),
            notifications=_build(NotificationConfig, data.get("notifications", {})),
        )

        # Resolve secrets for IMAP username and password
        from email_supervisor.utils.security import resolve_secret
        config.imap.username = resolve_secret(config.imap.username)
        config.imap.password = resolve_secret(config.imap.password)

        # Log resolved secrets
        logging.debug(f"Resolved username: {config.imap.username}")
        logging.debug(f"Resolved password: {config.imap.password}")

        return config


def _build(cls: type, data: dict):  # noqa: ANN202
    """Construct a dataclass from a dict, ignoring unknown keys."""
    import dataclasses

    valid_keys = {f.name for f in dataclasses.fields(cls)}
    return cls(**{k: v for k, v in data.items() if k in valid_keys})
