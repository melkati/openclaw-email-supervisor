"""Global constants shared across the application."""

from __future__ import annotations

# ── version ───────────────────────────────────────────────────
VERSION = "0.1.0"

# ── defaults ──────────────────────────────────────────────────
DEFAULT_POLL_INTERVAL_S = 120
DEFAULT_BATCH_SIZE = 50
DEFAULT_MAX_AGE_H = 72
DEFAULT_MAX_PROCESSED_IDS = 50_000
DEFAULT_AI_MAX_TOKENS_PER_DAY = 5_000
DEFAULT_LEARNING_WINDOW_DAYS = 30

# ── token optimizer ───────────────────────────────────────────
SHORT_SNIPPET_CHARS = 500
LONG_SNIPPET_CHARS = 1_000
HIGH_CONFIDENCE = 0.9
MEDIUM_CONFIDENCE = 0.5

# ── sender scorer ─────────────────────────────────────────────
SENDER_SCORE_BLACKLIST_THRESHOLD = -0.8
SENDER_SCORE_WHITELIST_THRESHOLD = 0.8
SENDER_SCORE_TAU = 5.0  # smoothing factor

# ── rule engine ───────────────────────────────────────────────
BUILTIN_RULE_PREFIX = "_builtin_"
SHADOW_RULE_MIN_ACCURACY = 0.95

# ── reconnection ──────────────────────────────────────────────
IMAP_BACKOFF_BASE_S = 1.0
IMAP_BACKOFF_MAX_S = 300.0  # 5 minutes
IMAP_FETCH_RETRIES = 2

# ── persistence ───────────────────────────────────────────────
FLUSH_INTERVAL_S = 30
FLUSH_BATCH_SIZE = 20

# ── logging ───────────────────────────────────────────────────
LOG_MAX_BYTES = 50 * 1024 * 1024  # 50 MB
LOG_BACKUP_COUNT = 7

# ── telegram ──────────────────────────────────────────────────
TELEGRAM_RATE_LIMIT_PER_MIN = 30
