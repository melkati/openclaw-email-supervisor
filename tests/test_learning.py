"""Tests for the learning engine — frequency analysis, sender scoring, rule generation."""

from __future__ import annotations

import pytest
from datetime import datetime, timezone

from email_supervisor.models.email_message import EmailMessage
from email_supervisor.models.classification import Label, ClassifiedBy, ClassificationResult
from email_supervisor.learning.frequency_analyzer import FrequencyAnalyzer
from email_supervisor.learning.sender_scorer import SenderScorer


def _make_email(from_addr: str = "sender@example.com", subject: str = "Test", **kw) -> EmailMessage:
    defaults = dict(
        uid="1",
        message_id="<1@test>",
        account_id="test",
        folder="INBOX",
        from_address=from_addr,
        from_display="Sender",
        to_addresses=["user@test.local"],
        cc_addresses=[],
        subject=subject,
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


def _make_result(label: Label = Label.NEUTRAL) -> ClassificationResult:
    return ClassificationResult(
        label=label,
        confidence=0.9,
        classified_by=ClassifiedBy.RULE_ENGINE,
        rule_id=None,
        reason="test",
    )


class TestFrequencyAnalyzer:
    def test_record_and_top_domains(self):
        analyzer = FrequencyAnalyzer()
        for _ in range(5):
            analyzer.record(
                _make_email(from_addr="a@example.com"),
                _make_result(Label.NEUTRAL),
            )
        for _ in range(3):
            analyzer.record(
                _make_email(from_addr="b@spam.net"),
                _make_result(Label.SPAM),
            )
        top = analyzer.top_domains(n=5)
        assert top[0][0] == "example.com"
        assert top[0][1] == 5

    def test_spam_subject_tokens(self):
        analyzer = FrequencyAnalyzer()
        for _ in range(10):
            analyzer.record(
                _make_email(subject="FREE money guaranteed"),
                _make_result(Label.SPAM),
            )
        spam_tokens = analyzer.top_spam_subject_tokens(n=5)
        token_words = [t[0] for t in spam_tokens]
        assert "free" in token_words or "money" in token_words or "guaranteed" in token_words


class TestSenderScorer:
    def test_score_increases_with_important(self):
        scorer = SenderScorer()
        for _ in range(10):
            scorer.record("alice@corp.com", Label.IMPORTANT)
        score = scorer.get_score("alice@corp.com")
        assert score > 0.5

    def test_score_decreases_with_spam(self):
        scorer = SenderScorer()
        for _ in range(10):
            scorer.record("spammer@evil.net", Label.SPAM)
        score = scorer.get_score("spammer@evil.net")
        assert score < -0.5

    def test_auto_blacklist_candidates(self):
        scorer = SenderScorer()
        for _ in range(20):
            scorer.record("badactor@evil.net", Label.SPAM)
        candidates = scorer.get_auto_blacklist_candidates()
        assert "badactor@evil.net" in candidates

    def test_auto_whitelist_candidates(self):
        scorer = SenderScorer()
        for _ in range(20):
            scorer.record("trusted@corp.com", Label.IMPORTANT)
        candidates = scorer.get_auto_whitelist_candidates()
        assert "trusted@corp.com" in candidates

    def test_unknown_sender_returns_zero(self):
        scorer = SenderScorer()
        assert scorer.get_score("unknown@nowhere.com") == 0.0
