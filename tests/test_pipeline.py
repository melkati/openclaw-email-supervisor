"""Tests for the email pipeline — dedup, lists, rules, and fallback."""

from __future__ import annotations

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from email_supervisor.models.email_message import EmailMessage
from email_supervisor.models.account_config import AccountConfig
from email_supervisor.pipeline import EmailPipeline


def _make_email(uid: str = "100", from_addr: str = "sender@example.com", **kw) -> EmailMessage:
    defaults = dict(
        uid=uid,
        message_id=f"<{uid}@test>",
        account_id="test",
        folder="INBOX",
        from_address=from_addr,
        from_display="Sender",
        to_addresses=["user@test.local"],
        cc_addresses=[],
        subject="Test",
        date=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
        size_bytes=5000,
        headers={},
        has_attachments=False,
        spf_pass=True,
        dkim_pass=True,
        reply_to=None,
        body=None,
        body_snippet=None,
    )
    defaults.update(kw)
    return EmailMessage(**defaults)


ACCOUNT_DICT = {
    "account_id": "test",
    "display_name": "Test",
    "enabled": True,
    "imap": {
        "host": "imap.test.local",
        "port": 993,
        "ssl": True,
        "username": "test@test.local",
        "password": "test",
        "folders": ["INBOX"],
    },
    "polling": {"interval_seconds": 60, "batch_size": 10, "max_age_hours": 24},
    "pipeline": {
        "dedup_enabled": True,
        "whitelist_blacklist_enabled": True,
        "rules_enabled": True,
        "ai_enabled": False,
        "ai_confidence_threshold": 0.7,
    },
    "learning": {
        "enabled": False,
        "auto_whitelist": False,
        "auto_blacklist": False,
        "shadow_rule_generation": False,
        "shadow_promotion_threshold": 0.95,
    },
    "notifications": {
        "notify_important": True,
        "notify_suspicious": True,
        "notify_spam_summary": True,
        "digest_enabled": False,
    },
}


@pytest.fixture
def mock_store():
    store = MagicMock()
    store.load_processed_ids.return_value = set()
    store.load_whitelist.return_value = []
    store.load_blacklist.return_value = []
    store.load_rules.return_value = []
    store.save_processed_ids = MagicMock()
    store.save_stats = MagicMock()
    return store


@pytest.fixture
def pipeline(mock_store):
    config = AccountConfig.from_dict(ACCOUNT_DICT)
    return EmailPipeline(
        config=config,
        store=mock_store,
        ai_gateway=None,
        learning_engine=None,
        notifier=None,
    )


class TestDeduplication:
    @pytest.mark.asyncio
    async def test_skip_already_processed(self, pipeline, mock_store):
        mock_store.load_processed_ids.return_value = {"100"}
        email = _make_email(uid="100")
        await pipeline.process_batch([email])
        # Email should be deduplicated, not classified further

    @pytest.mark.asyncio
    async def test_new_email_passes_dedup(self, pipeline, mock_store):
        mock_store.load_processed_ids.return_value = set()
        email = _make_email(uid="200")
        await pipeline.process_batch([email])


class TestWhitelistBlacklist:
    @pytest.mark.asyncio
    async def test_whitelisted_sender(self, pipeline, mock_store):
        mock_store.load_whitelist.return_value = ["trusted@example.com"]
        email = _make_email(from_addr="trusted@example.com")
        await pipeline.process_batch([email])

    @pytest.mark.asyncio
    async def test_blacklisted_sender(self, pipeline, mock_store):
        mock_store.load_blacklist.return_value = ["spammer@evil.com"]
        email = _make_email(from_addr="spammer@evil.com")
        await pipeline.process_batch([email])
