"""Test fixtures and sample data."""

from __future__ import annotations

import pytest
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_emails():
    """Load sample email data from fixtures."""
    import json
    path = FIXTURES_DIR / "sample_emails.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def tmp_data_dir(tmp_path):
    """Provide a temporary data directory with expected structure."""
    (tmp_path / "accounts").mkdir()
    (tmp_path / "logs").mkdir()
    return tmp_path


@pytest.fixture
def tmp_config_dir(tmp_path):
    """Provide a temporary config directory with an account."""
    import json
    cfg_root = tmp_path / "config"
    cfg_root.mkdir()
    accounts_dir = cfg_root / "accounts"
    accounts_dir.mkdir()

    account = {
        "account_id": "test-account",
        "display_name": "Test Account",
        "enabled": True,
        "imap": {
            "host": "imap.test.local",
            "port": 993,
            "ssl": True,
            "username": "test@test.local",
            "password": "test-password",
            "folders": ["INBOX"],
        },
        "polling": {
            "interval_seconds": 60,
            "batch_size": 10,
            "max_age_hours": 24,
        },
        "pipeline": {
            "dedup_enabled": True,
            "whitelist_blacklist_enabled": True,
            "rules_enabled": True,
            "ai_enabled": False,
            "ai_confidence_threshold": 0.7,
        },
        "learning": {
            "enabled": True,
            "auto_whitelist": True,
            "auto_blacklist": True,
            "shadow_rule_generation": True,
            "shadow_promotion_threshold": 0.95,
        },
        "notifications": {
            "notify_important": True,
            "notify_suspicious": True,
            "notify_spam_summary": True,
            "digest_enabled": False,
        },
    }
    (accounts_dir / "test-account.json").write_text(
        json.dumps(account, indent=2), encoding="utf-8"
    )
    return cfg_root
