"""Prompt templates for AI classification.

All templates are designed for extreme token efficiency:
- Compact system instructions
- Structured output format (JSON)
- Only the minimum context needed
"""

from __future__ import annotations

SYSTEM_PROMPT = (
    "You classify emails. "
    "Labels: spam, important, neutral, suspicious. "
    "Respond ONLY with JSON: "
    '{"label":"...","confidence":0.0-1.0,"reason":"max 15 words"}'
)

CLASSIFICATION_TEMPLATE = (
    "From: {sender}\n"
    "Subject: {subject}\n"
    "Flags: {flags}\n"
    "Snippet:\n{snippet}"
)


def build_classification_prompt(
    sender: str,
    subject: str,
    flags: list[str],
    snippet: str,
) -> str:
    """Build a compact classification prompt from email components."""
    flags_str = ", ".join(flags) if flags else "none"
    return CLASSIFICATION_TEMPLATE.format(
        sender=sender,
        subject=subject[:150],  # hard trim subject
        flags=flags_str,
        snippet=snippet,
    )
