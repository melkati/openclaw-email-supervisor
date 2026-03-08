"""Structured JSON logging configuration.

Every log line is a single JSON object written to a RotatingFileHandler
and (optionally) to stderr for development.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from email_supervisor.utils.constants import LOG_BACKUP_COUNT, LOG_MAX_BYTES


class _JSONFormatter(logging.Formatter):
    """Emit each record as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "component": getattr(record, "component", record.name),
            "event": record.getMessage(),
        }
        # Merge any extra fields attached by the caller
        for key in ("account", "msg_id", "classification", "classified_by",
                     "rule_id", "ai_tokens_used", "latency_ms",
                     "subject_hash", "from_addr"):
            value = getattr(record, key, None)
            if value is not None:
                entry[key] = value

        if record.exc_info and record.exc_info[1]:
            entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(entry, ensure_ascii=False)


def setup_logging(
    log_dir: Optional[str | Path] = None,
    level: int = logging.INFO,
    console: bool = True,
) -> logging.Logger:
    """Configure the root ``email_supervisor`` logger.

    Parameters
    ----------
    log_dir:
        Directory for the rotating ``.jsonl`` log file.  If *None*,
        falls back to ``$EMAIL_SUPERVISOR_CONFIG_PATH/../data/logs``
        or the current working directory.
    level:
        Minimum log level.
    console:
        If *True*, also log human-readable lines to stderr.
    """
    if log_dir is None:
        config_path = os.environ.get("EMAIL_SUPERVISOR_CONFIG_PATH", "")
        if config_path:
            log_dir = Path(config_path).parent / "data" / "logs"
        else:
            log_dir = Path.cwd() / "data" / "logs"
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("email_supervisor")
    logger.setLevel(level)
    logger.handlers.clear()

    # ── file handler (JSON Lines) ─────────────────────────────
    fh = logging.handlers.RotatingFileHandler(
        log_dir / "supervisor.jsonl",
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    fh.setFormatter(_JSONFormatter())
    logger.addHandler(fh)

    # ── console handler (human readable) ──────────────────────
    if console:
        ch = logging.StreamHandler(sys.stderr)
        ch.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)-7s [%(name)s] %(message)s",
                datefmt="%H:%M:%S",
            )
        )
        logger.addHandler(ch)

    return logger


def get_logger(component: str) -> logging.Logger:
    """Return a child logger for a specific component.

    Usage::

        log = get_logger("pipeline")
        log.info("email_classified", extra={"account": "work", ...})
    """
    return logging.getLogger(f"email_supervisor.{component}")
