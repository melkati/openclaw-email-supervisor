"""Condition evaluators for the rule engine DSL.

Each condition is a dict like::

    {"field": "sender_domain", "op": "in", "value": ["example.com"]}

The :func:`evaluate_condition` function dispatches to the correct
operator implementation based on ``op``.
"""

from __future__ import annotations

import re
from typing import Any

from email_supervisor.models.email_message import EmailMessage


# ── field resolver ────────────────────────────────────────────

def _resolve_field(msg: EmailMessage, field_name: str) -> Any:
    """Extract a value from an EmailMessage by field name.

    Supports dotted paths for headers, e.g. ``headers.X-Mailer``.
    """
    # Direct attribute lookup
    if hasattr(msg, field_name):
        return getattr(msg, field_name)

    # Header lookup (e.g. "headers.X-Mailer")
    if field_name.startswith("headers."):
        header_name = field_name.split(".", 1)[1]
        mapping = {
            "x-mailer": msg.x_mailer,
            "list-unsubscribe": msg.list_unsubscribe,
            "spf": msg.spf_result,
            "dkim": msg.dkim_result,
        }
        return mapping.get(header_name.lower(), "")

    return None


# ── operator implementations ─────────────────────────────────

def _op_equals(actual: Any, expected: Any) -> bool:
    if isinstance(actual, str) and isinstance(expected, str):
        return actual.lower() == expected.lower()
    return actual == expected


def _op_not_equals(actual: Any, expected: Any) -> bool:
    return not _op_equals(actual, expected)


def _op_contains(actual: Any, expected: Any) -> bool:
    if isinstance(actual, str) and isinstance(expected, str):
        return expected.lower() in actual.lower()
    return False


def _op_not_contains(actual: Any, expected: Any) -> bool:
    return not _op_contains(actual, expected)


def _op_starts_with(actual: Any, expected: Any) -> bool:
    if isinstance(actual, str) and isinstance(expected, str):
        return actual.lower().startswith(expected.lower())
    return False


def _op_ends_with(actual: Any, expected: Any) -> bool:
    if isinstance(actual, str) and isinstance(expected, str):
        return actual.lower().endswith(expected.lower())
    return False


def _op_regex(actual: Any, expected: Any) -> bool:
    if isinstance(actual, str) and isinstance(expected, str):
        try:
            return bool(re.search(expected, actual, re.IGNORECASE))
        except re.error:
            return False
    return False


def _op_in(actual: Any, expected: Any) -> bool:
    """True if actual is in the expected list."""
    if isinstance(expected, list):
        if isinstance(actual, str):
            return actual.lower() in [str(v).lower() for v in expected]
        return actual in expected
    return False


def _op_not_in(actual: Any, expected: Any) -> bool:
    return not _op_in(actual, expected)


def _op_gt(actual: Any, expected: Any) -> bool:
    try:
        return float(actual) > float(expected)
    except (TypeError, ValueError):
        return False


def _op_lt(actual: Any, expected: Any) -> bool:
    try:
        return float(actual) < float(expected)
    except (TypeError, ValueError):
        return False


def _op_gte(actual: Any, expected: Any) -> bool:
    try:
        return float(actual) >= float(expected)
    except (TypeError, ValueError):
        return False


def _op_lte(actual: Any, expected: Any) -> bool:
    try:
        return float(actual) <= float(expected)
    except (TypeError, ValueError):
        return False


def _op_eq(actual: Any, expected: Any) -> bool:
    try:
        return float(actual) == float(expected)
    except (TypeError, ValueError):
        return _op_equals(actual, expected)


def _op_between(actual: Any, expected: Any) -> bool:
    """True if actual is between expected[0] and expected[1] inclusive."""
    if isinstance(expected, list) and len(expected) >= 2:
        try:
            val = float(actual)
            return float(expected[0]) <= val <= float(expected[1])
        except (TypeError, ValueError):
            return False
    return False


def _op_is(actual: Any, expected: Any) -> bool:
    """Boolean check — ``{"field": "has_attachments", "op": "is", "value": true}``."""
    return bool(actual) == bool(expected)


def _op_exists(actual: Any, _expected: Any) -> bool:
    """True if the field is non-empty."""
    if isinstance(actual, str):
        return len(actual.strip()) > 0
    return actual is not None


def _op_not_exists(actual: Any, expected: Any) -> bool:
    return not _op_exists(actual, expected)


def _op_length_gt(actual: Any, expected: Any) -> bool:
    try:
        return len(str(actual)) > int(expected)
    except (TypeError, ValueError):
        return False


def _op_length_lt(actual: Any, expected: Any) -> bool:
    try:
        return len(str(actual)) < int(expected)
    except (TypeError, ValueError):
        return False


# ── operator registry ─────────────────────────────────────────

_OPERATORS: dict[str, Any] = {
    "equals": _op_equals,
    "not_equals": _op_not_equals,
    "contains": _op_contains,
    "not_contains": _op_not_contains,
    "starts_with": _op_starts_with,
    "ends_with": _op_ends_with,
    "regex": _op_regex,
    "in": _op_in,
    "not_in": _op_not_in,
    "gt": _op_gt,
    "lt": _op_lt,
    "gte": _op_gte,
    "lte": _op_lte,
    "eq": _op_eq,
    "between": _op_between,
    "is": _op_is,
    "exists": _op_exists,
    "not_exists": _op_not_exists,
    "length_gt": _op_length_gt,
    "length_lt": _op_length_lt,
}


# ── public API ────────────────────────────────────────────────

def evaluate_condition(msg: EmailMessage, condition: dict) -> bool:
    """Evaluate a single condition dict against an EmailMessage.

    Parameters
    ----------
    msg:
        The email to test.
    condition:
        A dict with ``field``, ``op``, and ``value`` keys.

    Returns
    -------
    bool
        Whether the condition matches.
    """
    field_name = condition.get("field", "")
    op_name = condition.get("op", "")
    expected = condition.get("value")

    actual = _resolve_field(msg, field_name)
    op_fn = _OPERATORS.get(op_name)
    if op_fn is None:
        return False

    try:
        return op_fn(actual, expected)
    except Exception:
        return False


def evaluate_group(msg: EmailMessage, group: dict) -> bool:
    """Evaluate a condition group (AND / OR / NOT) recursively.

    A group looks like::

        {"operator": "AND", "items": [<condition_or_group>, ...]}
    """
    operator = group.get("operator", "AND").upper()
    items = group.get("items", [])

    if not items:
        return True  # empty group matches everything

    results = []
    for item in items:
        if "operator" in item:
            results.append(evaluate_group(msg, item))
        else:
            results.append(evaluate_condition(msg, item))

    if operator == "AND":
        return all(results)
    elif operator == "OR":
        return any(results)
    elif operator == "NOT":
        # NOT applies to the first item only
        return not results[0] if results else True
    else:
        return False
