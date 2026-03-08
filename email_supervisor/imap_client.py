"""Async IMAP client wrapper.

Provides a high-level interface over :pypi:`aioimaplib` for connecting
to an IMAP server, fetching new UIDs, downloading envelopes, and
(lazily) fetching message bodies.

The client handles:
- TLS connections
- IDLE vs POLL mode
- Exponential backoff on connection loss
- Parsing ENVELOPE data into :class:`EmailMessage` instances
"""

from __future__ import annotations

import asyncio
import email
import email.header
import email.utils
import re
from datetime import datetime, timezone
from typing import Optional

from email_supervisor.models.account_config import IMAPConfig
from email_supervisor.models.email_message import EmailMessage
from email_supervisor.utils.constants import (
    IMAP_BACKOFF_BASE_S,
    IMAP_BACKOFF_MAX_S,
    IMAP_FETCH_RETRIES,
)
from email_supervisor.utils.logging_config import get_logger
from email_supervisor.utils.security import resolve_secret

log = get_logger("imap_client")

# Try to import aioimaplib; provide helpful error if missing
try:
    import aioimaplib
except ImportError:
    aioimaplib = None  # type: ignore[assignment]


class IMAPClientError(Exception):
    """Raised on unrecoverable IMAP errors (e.g. bad credentials)."""


class IMAPClient:
    """Async IMAP client with reconnection and lazy body fetch."""

    def __init__(self, config: IMAPConfig, account_id: str) -> None:
        self._config = config
        self._account_id = account_id
        self._client: Optional[aioimaplib.IMAP4_SSL | aioimaplib.IMAP4] = None
        self._backoff = IMAP_BACKOFF_BASE_S
        self._connected = False

    # ── connection lifecycle ──────────────────────────────────

    async def connect(self) -> None:
        """Establish (or re-establish) the IMAP connection."""
        if aioimaplib is None:
            raise ImportError(
                "aioimaplib is required. Install it: pip install aioimaplib"
            )

        password = resolve_secret(self._config.password_ref)

        try:
            if self._config.tls:
                self._client = aioimaplib.IMAP4_SSL(
                    host=self._config.host,
                    port=self._config.port,
                )
            else:
                log.warning(
                    "TLS disabled for %s — connection is NOT encrypted",
                    self._account_id,
                )
                self._client = aioimaplib.IMAP4(
                    host=self._config.host,
                    port=self._config.port,
                )

            await self._client.wait_hello_from_server()
            resp = await self._client.login(self._config.username, password)

            if resp.result != "OK":
                raise IMAPClientError(
                    f"Authentication failed for {self._account_id}: {resp.lines}"
                )

            self._connected = True
            self._backoff = IMAP_BACKOFF_BASE_S
            log.info(
                "Connected to %s:%d for account %s",
                self._config.host,
                self._config.port,
                self._account_id,
            )

        except IMAPClientError:
            raise  # Don't retry auth errors
        except Exception as exc:
            self._connected = False
            log.error(
                "Connection failed for %s: %s", self._account_id, exc
            )
            raise

    async def disconnect(self) -> None:
        """Gracefully close the IMAP connection."""
        if self._client and self._connected:
            try:
                await self._client.logout()
            except Exception:
                pass
        self._connected = False
        self._client = None

    async def reconnect(self) -> None:
        """Reconnect with exponential backoff."""
        await self.disconnect()
        log.info(
            "Reconnecting %s in %.1fs …", self._account_id, self._backoff
        )
        await asyncio.sleep(self._backoff)
        self._backoff = min(self._backoff * 2, IMAP_BACKOFF_MAX_S)
        await self.connect()

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ── fetching ──────────────────────────────────────────────

    async def select_folder(self, folder: str = "INBOX") -> int:
        """Select a folder; return the message count."""
        assert self._client is not None
        resp = await self._client.select(folder)
        if resp.result != "OK":
            raise IMAPClientError(f"Cannot select {folder}: {resp.lines}")
        # Parse EXISTS count from response
        for line in resp.lines:
            if isinstance(line, bytes):
                line = line.decode()
            match = re.search(r"(\d+)\s+EXISTS", str(line))
            if match:
                return int(match.group(1))
        return 0

    async def fetch_new_uids(
        self, folder: str = "INBOX", since: Optional[datetime] = None
    ) -> list[str]:
        """Return UIDs of messages in *folder* newer than *since*.

        If *since* is None, fetches all UIDs in the folder.
        """
        assert self._client is not None
        await self.select_folder(folder)

        if since:
            date_str = since.strftime("%d-%b-%Y")
            criteria = f"SINCE {date_str}"
        else:
            criteria = "ALL"

        resp = await self._client.uid_search(criteria)
        if resp.result != "OK":
            log.warning("UID SEARCH failed for %s: %s", self._account_id, resp.lines)
            return []

        # resp.lines[0] is a space-separated list of UIDs
        raw = resp.lines[0] if resp.lines else b""
        if isinstance(raw, bytes):
            raw = raw.decode()
        uids = raw.strip().split()
        return [uid for uid in uids if uid]

    async def fetch_headers(self, uids: list[str]) -> list[EmailMessage]:
        """Fetch ENVELOPE + selected headers for the given UIDs.

        Returns one :class:`EmailMessage` per UID with metadata populated
        but ``body`` left as *None* (lazy fetch).
        """
        if not uids:
            return []
        assert self._client is not None

        messages: list[EmailMessage] = []
        uid_set = ",".join(uids)

        for attempt in range(1, IMAP_FETCH_RETRIES + 1):
            try:
                resp = await self._client.uid(
                    "fetch",
                    uid_set,
                    "(UID FLAGS RFC822.SIZE BODY.PEEK[HEADER])",
                )
                if resp.result != "OK":
                    log.warning("FETCH failed (attempt %d): %s", attempt, resp.lines)
                    continue
                messages = self._parse_header_responses(resp.lines, uids)
                break
            except Exception as exc:
                log.warning("FETCH error (attempt %d): %s", attempt, exc)
                if attempt == IMAP_FETCH_RETRIES:
                    raise
        return messages

    async def fetch_body(self, uid: str) -> Optional[str]:
        """Fetch the plain-text body of a single message by UID."""
        assert self._client is not None
        try:
            resp = await self._client.uid(
                "fetch", uid, "(BODY.PEEK[TEXT])"
            )
            if resp.result != "OK":
                return None
            for item in resp.lines:
                if isinstance(item, bytes) and len(item) > 50:
                    return item.decode("utf-8", errors="replace")
            return None
        except Exception as exc:
            log.warning("Body fetch failed for UID %s: %s", uid, exc)
            return None

    # ── IDLE support ──────────────────────────────────────────

    async def idle_wait(self, timeout: int = 300) -> bool:
        """Enter IMAP IDLE and wait for new mail or timeout.

        Returns True if new mail was signalled, False on timeout.
        """
        assert self._client is not None
        if not self._config.idle_supported:
            await asyncio.sleep(timeout)
            return False

        try:
            idle_task = await self._client.idle_start(timeout=timeout)
            resp = await self._client.wait_server_push()
            self._client.idle_done()
            await asyncio.wait_for(idle_task, timeout=10)

            for line in resp:
                line_str = line.decode() if isinstance(line, bytes) else str(line)
                if "EXISTS" in line_str:
                    return True
            return False
        except (asyncio.TimeoutError, Exception) as exc:
            log.debug("IDLE interrupted for %s: %s", self._account_id, exc)
            return False

    # ── parsing helpers ───────────────────────────────────────

    def _parse_header_responses(
        self, lines: list, uids: list[str]
    ) -> list[EmailMessage]:
        """Parse raw FETCH responses into EmailMessage objects."""
        messages: list[EmailMessage] = []
        i = 0

        while i < len(lines):
            line = lines[i]
            if isinstance(line, bytes):
                line = line.decode("utf-8", errors="replace")

            # Look for the header data (usually the next element is bytes)
            if "HEADER" in str(line) and i + 1 < len(lines):
                header_bytes = lines[i + 1]
                if isinstance(header_bytes, bytes):
                    msg = self._parse_single_header(header_bytes, line)
                    if msg:
                        messages.append(msg)
                i += 2
            else:
                i += 1

        return messages

    def _parse_single_header(
        self, header_bytes: bytes, meta_line: str
    ) -> Optional[EmailMessage]:
        """Parse one email header block into an EmailMessage."""
        try:
            parsed = email.message_from_bytes(header_bytes)

            # Extract UID from meta line
            uid_match = re.search(r"UID\s+(\d+)", meta_line)
            uid = uid_match.group(1) if uid_match else ""

            # Extract FLAGS
            flags_match = re.search(r"FLAGS\s+\(([^)]*)\)", meta_line)
            flags = flags_match.group(1).split() if flags_match else []

            # Extract SIZE
            size_match = re.search(r"RFC822\.SIZE\s+(\d+)", meta_line)
            size = int(size_match.group(1)) if size_match else 0

            # Decode sender
            from_raw = parsed.get("From", "")
            sender = self._decode_header(from_raw)
            sender_domain = ""
            if "@" in sender:
                sender_domain = sender.rsplit("@", 1)[1].strip(">").lower()

            # Decode subject
            subject = self._decode_header(parsed.get("Subject", ""))

            # Parse date
            date_str = parsed.get("Date", "")
            msg_date = None
            if date_str:
                try:
                    parsed_date = email.utils.parsedate_to_datetime(date_str)
                    msg_date = parsed_date.astimezone(timezone.utc)
                except Exception:
                    pass

            # To / CC
            to_raw = parsed.get("To", "")
            cc_raw = parsed.get("Cc", "")
            to_list = [a.strip() for a in to_raw.split(",") if a.strip()] if to_raw else []
            cc_list = [a.strip() for a in cc_raw.split(",") if a.strip()] if cc_raw else []

            return EmailMessage(
                uid=uid,
                message_id=parsed.get("Message-ID", uid),
                sender=sender,
                sender_domain=sender_domain,
                to=to_list,
                cc=cc_list,
                subject=subject,
                date=msg_date,
                reply_to=parsed.get("Reply-To", ""),
                x_mailer=parsed.get("X-Mailer", ""),
                list_unsubscribe=parsed.get("List-Unsubscribe", ""),
                spf_result=self._extract_auth_result(parsed, "spf"),
                dkim_result=self._extract_auth_result(parsed, "dkim"),
                content_type=parsed.get("Content-Type", ""),
                size_bytes=size,
                has_attachments="attachment" in parsed.get("Content-Type", "").lower(),
                flags=flags,
            )
        except Exception as exc:
            log.warning("Failed to parse header: %s", exc)
            return None

    @staticmethod
    def _decode_header(raw: str) -> str:
        """Decode RFC2047-encoded header value."""
        if not raw:
            return ""
        try:
            parts = email.header.decode_header(raw)
            decoded = []
            for part, charset in parts:
                if isinstance(part, bytes):
                    decoded.append(part.decode(charset or "utf-8", errors="replace"))
                else:
                    decoded.append(part)
            return " ".join(decoded)
        except Exception:
            return raw

    @staticmethod
    def _extract_auth_result(parsed: email.message.Message, method: str) -> str:
        """Extract SPF or DKIM result from Authentication-Results header."""
        auth = parsed.get("Authentication-Results", "")
        if not auth:
            return ""
        pattern = rf"{method}=(\w+)"
        match = re.search(pattern, auth, re.IGNORECASE)
        return match.group(1).lower() if match else ""
