"""Tests for the persistence layer — JSONStore."""

from __future__ import annotations

import json
import pytest
from pathlib import Path

from email_supervisor.persistence.json_store import JSONStore


@pytest.fixture
def store(tmp_path):
    """Create a JSONStore with temporary directories."""
    data_root = tmp_path / "data"
    config_root = tmp_path / "config"
    data_root.mkdir()
    config_root.mkdir()
    (config_root / "accounts").mkdir()
    return JSONStore(data_root=data_root, config_root=config_root)


class TestProcessedIds:
    def test_save_and_load(self, store):
        ids = {"uid1", "uid2", "uid3"}
        store.save_processed_ids("acct1", ids)
        loaded = store.load_processed_ids("acct1")
        assert loaded == ids

    def test_empty_on_missing(self, store):
        loaded = store.load_processed_ids("nonexistent")
        assert loaded == set()


class TestWhitelistBlacklist:
    def test_whitelist_roundtrip(self, store):
        entries = ["alice@example.com", "@trusted.com", "/^vip-.*/"]
        store.save_whitelist("acct1", entries)
        loaded = store.load_whitelist("acct1")
        assert loaded == entries

    def test_blacklist_roundtrip(self, store):
        entries = ["spam@evil.com", "@bad-domain.net"]
        store.save_blacklist("acct1", entries)
        loaded = store.load_blacklist("acct1")
        assert loaded == entries


class TestRules:
    def test_rules_roundtrip(self, store):
        rules = [
            {
                "id": "r1",
                "name": "Test Rule",
                "enabled": True,
                "shadow": False,
                "priority": 10,
                "condition": {"operator": "AND", "conditions": []},
                "action": {"label": "SPAM", "terminal": True},
            }
        ]
        store.save_rules("acct1", rules)
        loaded = store.load_rules("acct1")
        assert len(loaded) == 1
        assert loaded[0]["id"] == "r1"


class TestSenderScores:
    def test_scores_roundtrip(self, store):
        scores = {"alice@example.com": 0.85, "spammer@evil.net": -0.92}
        store.save_sender_scores("acct1", scores)
        loaded = store.load_sender_scores("acct1")
        assert abs(loaded["alice@example.com"] - 0.85) < 0.001


class TestStats:
    def test_stats_roundtrip(self, store):
        stats = {"total_processed": 150, "total_spam": 42}
        store.save_stats("acct1", stats)
        loaded = store.load_stats("acct1")
        assert loaded["total_processed"] == 150
