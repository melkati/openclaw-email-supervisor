"""Tests for the AI token optimizer."""

from __future__ import annotations

import pytest
from datetime import datetime, timezone

from email_supervisor.models.email_message import EmailMessage
from email_supervisor.ai.token_optimizer import TokenOptimizer


def _make_email(**overrides) -> EmailMessage:
    defaults = dict(
        uid="1",
        message_id="<1@test>",
        account_id="test",
        folder="INBOX",
        from_address="sender@example.com",
        from_display="Sender",
        to_addresses=["user@test.local"],
        cc_addresses=[],
        subject="Test subject",
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
    defaults.update(overrides)
    return EmailMessage(**defaults)


class TestTokenOptimizer:
    def test_high_confidence_skips_body(self):
        """When metadata alone is high confidence, body should be skipped."""
        optimizer = TokenOptimizer()
        email = _make_email(
            spf_pass=False,
            dkim_pass=False,
            reply_to="scammer@evil.com",
            from_address="phish@bad-domain.com",
            subject="URGENT: Verify your account",
        )
        flags = optimizer.compute_metadata_flags(email)
        confidence = optimizer.estimate_metadata_confidence(flags)
        # With both SPF/DKIM fail and reply-to mismatch, confidence should be high
        assert confidence >= 0.7

    def test_low_confidence_includes_body(self):
        """Normal email should have lower metadata confidence."""
        optimizer = TokenOptimizer()
        email = _make_email(
            spf_pass=True,
            dkim_pass=True,
            subject="Weekly team update",
        )
        flags = optimizer.compute_metadata_flags(email)
        confidence = optimizer.estimate_metadata_confidence(flags)
        assert confidence < 0.7

    def test_snippet_truncation(self):
        """Snippet should be truncated to the configured size."""
        optimizer = TokenOptimizer()
        long_body = "A" * 5000
        email = _make_email(body_snippet=long_body)
        snippet = optimizer.prepare_snippet(email, max_chars=500)
        assert len(snippet) <= 510  # some tolerance for truncation marker

    def test_prepare_returns_dict(self):
        """prepare() should return a dict with metadata and optional snippet."""
        optimizer = TokenOptimizer()
        email = _make_email(body_snippet="Hello, just checking in.")
        result = optimizer.prepare(email)
        assert isinstance(result, dict)
        assert "from" in result
        assert "subject" in result

    def test_prepare_no_body_when_unnecessary(self):
        """Highly suspicious emails may skip body in prepare()."""
        optimizer = TokenOptimizer()
        email = _make_email(
            spf_pass=False,
            dkim_pass=False,
            reply_to="fake@scam.com",
            from_address="urgent@verify-now.com",
            subject="URGENT ACTION REQUIRED",
        )
        result = optimizer.prepare(email)
        # Should still return a valid dict regardless
        assert isinstance(result, dict)
