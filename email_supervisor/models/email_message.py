"""Lightweight representation of an email message (metadata-first)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass(slots=True)
class EmailMessage:
    """Immutable snapshot of an email.

    The pipeline operates on *metadata only* by default.  The full body
    is fetched lazily (see ``body`` / ``body_snippet``) and only when the
    AI gateway actually needs it.
    """

    # ── identity ──────────────────────────────────────────────
    uid: str
    message_id: str

    # ── envelope ──────────────────────────────────────────────
    sender: str = ""
    sender_domain: str = ""
    to: list[str] = field(default_factory=list)
    cc: list[str] = field(default_factory=list)
    subject: str = ""
    date: Optional[datetime] = None

    # ── headers (selected) ────────────────────────────────────
    reply_to: str = ""
    x_mailer: str = ""
    list_unsubscribe: str = ""
    spf_result: str = ""
    dkim_result: str = ""
    content_type: str = ""

    # ── size / structure ──────────────────────────────────────
    size_bytes: int = 0
    has_attachments: bool = False
    attachment_count: int = 0

    # ── flags ─────────────────────────────────────────────────
    flags: list[str] = field(default_factory=list)
    folder: str = "INBOX"

    # ── body (lazy) ───────────────────────────────────────────
    body: Optional[str] = None          # full text body (fetched on demand)
    body_snippet: Optional[str] = None  # first N chars (set by TokenOptimizer)

    # ── derived / computed ────────────────────────────────────
    @property
    def reply_to_mismatch(self) -> bool:
        """True when Reply-To is set and differs from sender."""
        if not self.reply_to:
            return False
        return self.reply_to.lower() != self.sender.lower()

    @property
    def hour(self) -> Optional[int]:
        """Hour of day (0-23) from the Date header."""
        return self.date.hour if self.date else None

    @property
    def day_of_week(self) -> Optional[int]:
        """Day of week (0=Monday … 6=Sunday) from the Date header."""
        return self.date.weekday() if self.date else None

    @property
    def cc_count(self) -> int:
        return len(self.cc)
