"""Tests for the rule engine — conditions, actions, and evaluation."""

from __future__ import annotations

import pytest
from datetime import datetime, timezone

from email_supervisor.models.email_message import EmailMessage
from email_supervisor.models.rule import Condition, ConditionGroup, Rule, RuleAction
from email_supervisor.rules.conditions import evaluate_condition, evaluate_group
from email_supervisor.rules.actions import build_action_plan
from email_supervisor.rules.engine import RuleEngine


def _make_email(**overrides) -> EmailMessage:
    """Create a test EmailMessage with sensible defaults."""
    defaults = dict(
        uid="100",
        message_id="<test@example.com>",
        account_id="test",
        folder="INBOX",
        from_address="sender@example.com",
        from_display="Sender Name",
        to_addresses=["user@test.local"],
        cc_addresses=[],
        subject="Test subject",
        date=datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc),
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


# ── Condition evaluation ──────────────────────────────────


class TestConditionEvaluation:
    def test_equals(self):
        email = _make_email(from_address="alice@example.com")
        cond = Condition(field="from_address", operator="equals", value="alice@example.com")
        assert evaluate_condition(cond, email) is True

    def test_equals_case_insensitive(self):
        email = _make_email(from_address="Alice@Example.com")
        cond = Condition(field="from_address", operator="equals", value="alice@example.com")
        assert evaluate_condition(cond, email) is True

    def test_contains(self):
        email = _make_email(subject="Important meeting tomorrow")
        cond = Condition(field="subject", operator="contains", value="meeting")
        assert evaluate_condition(cond, email) is True

    def test_not_contains(self):
        email = _make_email(subject="Regular update")
        cond = Condition(field="subject", operator="contains", value="meeting")
        assert evaluate_condition(cond, email) is False

    def test_regex(self):
        email = _make_email(subject="Invoice #12345 attached")
        cond = Condition(field="subject", operator="regex", value=r"Invoice\s+#\d+")
        assert evaluate_condition(cond, email) is True

    def test_greater_than(self):
        email = _make_email(size_bytes=150_000)
        cond = Condition(field="size_bytes", operator="gt", value=100_000)
        assert evaluate_condition(cond, email) is True

    def test_in_list(self):
        email = _make_email(from_address="vip@corp.com")
        cond = Condition(field="from_address", operator="in", value=["vip@corp.com", "boss@corp.com"])
        assert evaluate_condition(cond, email) is True

    def test_header_field(self):
        email = _make_email(headers={"X-Priority": "1"})
        cond = Condition(field="headers.X-Priority", operator="equals", value="1")
        assert evaluate_condition(cond, email) is True


class TestConditionGroup:
    def test_and_group(self):
        email = _make_email(from_address="alice@corp.com", subject="Urgent request")
        group = ConditionGroup(
            operator="AND",
            conditions=[
                Condition(field="from_address", operator="contains", value="corp.com"),
                Condition(field="subject", operator="contains", value="Urgent"),
            ],
        )
        assert evaluate_group(group, email) is True

    def test_and_group_partial_fail(self):
        email = _make_email(from_address="alice@corp.com", subject="Regular update")
        group = ConditionGroup(
            operator="AND",
            conditions=[
                Condition(field="from_address", operator="contains", value="corp.com"),
                Condition(field="subject", operator="contains", value="Urgent"),
            ],
        )
        assert evaluate_group(group, email) is False

    def test_or_group(self):
        email = _make_email(subject="Meeting invite")
        group = ConditionGroup(
            operator="OR",
            conditions=[
                Condition(field="subject", operator="contains", value="invoice"),
                Condition(field="subject", operator="contains", value="Meeting"),
            ],
        )
        assert evaluate_group(group, email) is True

    def test_not_group(self):
        email = _make_email(from_address="friend@safe.com")
        group = ConditionGroup(
            operator="NOT",
            conditions=[
                Condition(field="from_address", operator="contains", value="spam"),
            ],
        )
        assert evaluate_group(group, email) is True


# ── Rule engine ───────────────────────────────────────────


class TestRuleEngine:
    def test_reply_to_mismatch_builtin(self):
        email = _make_email(
            from_address="legit@company.com",
            reply_to="scammer@evil.com",
        )
        engine = RuleEngine(rules=[])
        terminal, additive = engine.evaluate(email)
        # The built-in reply-to mismatch rule should flag it
        assert any(a.label == "SUSPICIOUS" for a in additive)

    def test_no_spf_dkim_builtin(self):
        email = _make_email(spf_pass=False, dkim_pass=False)
        engine = RuleEngine(rules=[])
        terminal, additive = engine.evaluate(email)
        assert any(a.label == "SUSPICIOUS" for a in additive)

    def test_unsubscribe_header_builtin(self):
        email = _make_email(
            headers={"List-Unsubscribe": "<mailto:unsub@example.com>"}
        )
        engine = RuleEngine(rules=[])
        terminal, additive = engine.evaluate(email)
        assert any(a.label == "NEUTRAL" for a in additive)

    def test_custom_rule_terminal(self):
        rule = Rule(
            id="r1",
            name="block-spam-domain",
            enabled=True,
            shadow=False,
            priority=10,
            condition=ConditionGroup(
                operator="AND",
                conditions=[
                    Condition(field="from_address", operator="contains", value="@spam.net"),
                ],
            ),
            action=RuleAction(label="SPAM", terminal=True),
        )
        email = _make_email(from_address="bad@spam.net")
        engine = RuleEngine(rules=[rule])
        terminal, additive = engine.evaluate(email)
        assert terminal is not None
        assert terminal.label == "SPAM"

    def test_shadow_rule_not_terminal(self):
        rule = Rule(
            id="r2",
            name="shadow-test",
            enabled=True,
            shadow=True,
            priority=10,
            condition=ConditionGroup(
                operator="AND",
                conditions=[
                    Condition(field="from_address", operator="contains", value="@test.net"),
                ],
            ),
            action=RuleAction(label="SPAM", terminal=True),
        )
        email = _make_email(from_address="x@test.net")
        engine = RuleEngine(rules=[rule])
        terminal, additive = engine.evaluate(email)
        # Shadow rules should NOT produce a terminal action
        assert terminal is None
