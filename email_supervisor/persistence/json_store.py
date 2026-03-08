"""JSON-file backend for :class:`AccountStore`.

Each account gets its own directory under ``data/accounts/{account_id}/``
with one ``.json`` file per data category.  All writes are atomic
(write to temp → rename) to prevent corruption on crash.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from email_supervisor.persistence.store import AccountStore
from email_supervisor.utils.logging_config import get_logger

log = get_logger("json_store")


class JSONStore(AccountStore):
    """Flat-file JSON persistence backend."""

    def __init__(self, data_root: str | Path, config_root: str | Path) -> None:
        self._data_root = Path(data_root)
        self._config_root = Path(config_root)

    # ── internal helpers ──────────────────────────────────────

    def _account_dir(self, account_id: str) -> Path:
        d = self._data_root / "accounts" / account_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _read_json(self, path: Path, default: Any = None) -> Any:
        if not path.exists():
            return default if default is not None else {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            log.error("Failed to read %s: %s", path, exc)
            return default if default is not None else {}

    def _write_json(self, path: Path, data: Any) -> None:
        """Atomic write: temp file + rename."""
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            dir=str(path.parent), suffix=".tmp", prefix=".es_"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
            # On Windows, target must not exist for rename
            if path.exists():
                path.unlink()
            os.rename(tmp, str(path))
        except Exception:
            # Clean up temp on failure
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    # ── config ────────────────────────────────────────────────

    def load_config(self, account_id: str) -> dict:
        path = self._config_root / "accounts" / f"account_{account_id}.json"
        # Also try without the ``account_`` prefix
        if not path.exists():
            path = self._config_root / "accounts" / f"{account_id}.json"
        return self._read_json(path, default={})

    def save_config(self, account_id: str, data: dict) -> None:
        path = self._config_root / "accounts" / f"account_{account_id}.json"
        self._write_json(path, data)

    # ── processed IDs ─────────────────────────────────────────

    def _processed_path(self, account_id: str) -> Path:
        return self._account_dir(account_id) / "processed_ids.json"

    def is_processed(self, account_id: str, msg_id: str) -> bool:
        data = self._read_json(self._processed_path(account_id), default={})
        return msg_id in data.get("entries", {})

    def save_processed(self, account_id: str, msg_id: str, result: str) -> None:
        path = self._processed_path(account_id)
        data = self._read_json(path, default={"version": 1, "entries": {}})
        data.setdefault("entries", {})[msg_id] = {
            "ts": int(time.time()),
            "result": result,
        }
        self._write_json(path, data)

    def compact_processed(self, account_id: str, max_entries: int, max_age_s: int) -> int:
        path = self._processed_path(account_id)
        data = self._read_json(path, default={"version": 1, "entries": {}})
        entries: dict = data.get("entries", {})
        cutoff = int(time.time()) - max_age_s
        before = len(entries)

        # Remove by age
        entries = {k: v for k, v in entries.items() if v.get("ts", 0) > cutoff}

        # Remove oldest if still over limit
        if len(entries) > max_entries:
            sorted_items = sorted(entries.items(), key=lambda x: x[1].get("ts", 0))
            entries = dict(sorted_items[-max_entries:])

        data["entries"] = entries
        self._write_json(path, data)
        return before - len(entries)

    # ── whitelist ─────────────────────────────────────────────

    def _whitelist_path(self, account_id: str) -> Path:
        return self._account_dir(account_id) / "whitelist.json"

    def get_whitelist(self, account_id: str) -> list[dict]:
        data = self._read_json(self._whitelist_path(account_id), default={})
        return data.get("entries", [])

    def add_to_whitelist(self, account_id: str, entry: dict) -> None:
        path = self._whitelist_path(account_id)
        data = self._read_json(path, default={"version": 1, "entries": []})
        entries: list = data.setdefault("entries", [])
        # Prevent duplicates
        if any(e.get("pattern") == entry.get("pattern") for e in entries):
            return
        entry.setdefault("added_at", self._now_iso())
        entry.setdefault("hits", 0)
        entry.setdefault("confidence", 1.0)
        entries.append(entry)
        self._write_json(path, data)

    def remove_from_whitelist(self, account_id: str, pattern: str) -> bool:
        path = self._whitelist_path(account_id)
        data = self._read_json(path, default={"version": 1, "entries": []})
        entries: list = data.get("entries", [])
        before = len(entries)
        data["entries"] = [e for e in entries if e.get("pattern") != pattern]
        if len(data["entries"]) == before:
            return False
        self._write_json(path, data)
        return True

    def increment_whitelist_hit(self, account_id: str, pattern: str) -> None:
        path = self._whitelist_path(account_id)
        data = self._read_json(path, default={"version": 1, "entries": []})
        for entry in data.get("entries", []):
            if entry.get("pattern") == pattern:
                entry["hits"] = entry.get("hits", 0) + 1
                entry["last_hit"] = self._now_iso()
                break
        self._write_json(path, data)

    # ── blacklist ─────────────────────────────────────────────

    def _blacklist_path(self, account_id: str) -> Path:
        return self._account_dir(account_id) / "blacklist.json"

    def get_blacklist(self, account_id: str) -> list[dict]:
        data = self._read_json(self._blacklist_path(account_id), default={})
        return data.get("entries", [])

    def add_to_blacklist(self, account_id: str, entry: dict) -> None:
        path = self._blacklist_path(account_id)
        data = self._read_json(path, default={"version": 1, "entries": []})
        entries: list = data.setdefault("entries", [])
        if any(e.get("pattern") == entry.get("pattern") for e in entries):
            return
        entry.setdefault("added_at", self._now_iso())
        entry.setdefault("hits", 0)
        entry.setdefault("confidence", 1.0)
        entries.append(entry)
        self._write_json(path, data)

    def remove_from_blacklist(self, account_id: str, pattern: str) -> bool:
        path = self._blacklist_path(account_id)
        data = self._read_json(path, default={"version": 1, "entries": []})
        entries: list = data.get("entries", [])
        before = len(entries)
        data["entries"] = [e for e in entries if e.get("pattern") != pattern]
        if len(data["entries"]) == before:
            return False
        self._write_json(path, data)
        return True

    def increment_blacklist_hit(self, account_id: str, pattern: str) -> None:
        path = self._blacklist_path(account_id)
        data = self._read_json(path, default={"version": 1, "entries": []})
        for entry in data.get("entries", []):
            if entry.get("pattern") == pattern:
                entry["hits"] = entry.get("hits", 0) + 1
                entry["last_hit"] = self._now_iso()
                break
        self._write_json(path, data)

    # ── rules ─────────────────────────────────────────────────

    def _rules_path(self, account_id: str) -> Path:
        return self._account_dir(account_id) / "rules.json"

    def get_rules(self, account_id: str) -> list[dict]:
        data = self._read_json(self._rules_path(account_id), default={})
        rules = data.get("rules", [])
        return sorted(rules, key=lambda r: r.get("priority", 100))

    def upsert_rule(self, account_id: str, rule: dict) -> None:
        path = self._rules_path(account_id)
        data = self._read_json(path, default={"version": 1, "rules": []})
        rules: list = data.setdefault("rules", [])
        for i, existing in enumerate(rules):
            if existing.get("id") == rule.get("id"):
                rules[i] = rule
                self._write_json(path, data)
                return
        rules.append(rule)
        self._write_json(path, data)

    def delete_rule(self, account_id: str, rule_id: str) -> bool:
        path = self._rules_path(account_id)
        data = self._read_json(path, default={"version": 1, "rules": []})
        rules: list = data.get("rules", [])
        before = len(rules)
        data["rules"] = [r for r in rules if r.get("id") != rule_id]
        if len(data["rules"]) == before:
            return False
        self._write_json(path, data)
        return True

    def increment_rule_match(self, account_id: str, rule_id: str) -> None:
        path = self._rules_path(account_id)
        data = self._read_json(path, default={"version": 1, "rules": []})
        for rule in data.get("rules", []):
            if rule.get("id") == rule_id:
                stats = rule.setdefault("stats", {"matches": 0, "false_positives": 0})
                stats["matches"] = stats.get("matches", 0) + 1
                break
        self._write_json(path, data)

    # ── sender scores ─────────────────────────────────────────

    def _scores_path(self, account_id: str) -> Path:
        return self._account_dir(account_id) / "sender_scores.json"

    def get_sender_scores(self, account_id: str) -> dict[str, dict]:
        data = self._read_json(self._scores_path(account_id), default={})
        return data.get("scores", {})

    def get_sender_score(self, account_id: str, sender: str) -> Optional[dict]:
        return self.get_sender_scores(account_id).get(sender)

    def upsert_sender_score(self, account_id: str, sender: str, data_in: dict) -> None:
        path = self._scores_path(account_id)
        data = self._read_json(path, default={"scores": {}})
        data.setdefault("scores", {})[sender] = data_in
        self._write_json(path, data)

    # ── learning state ────────────────────────────────────────

    def _learning_path(self, account_id: str) -> Path:
        return self._account_dir(account_id) / "learning_state.json"

    def get_learning_state(self, account_id: str) -> dict:
        return self._read_json(self._learning_path(account_id), default={
            "pattern_buffer": {"subjects": {}, "domains": {}, "hours": {}, "sizes": {}},
            "pending_rules": [],
            "last_analysis": None,
        })

    def save_learning_state(self, account_id: str, state: dict) -> None:
        self._write_json(self._learning_path(account_id), state)

    # ── stats ─────────────────────────────────────────────────

    def _stats_path(self, account_id: str) -> Path:
        return self._account_dir(account_id) / "stats.json"

    def get_stats(self, account_id: str) -> dict:
        return self._read_json(self._stats_path(account_id), default={
            "total_processed": 0,
            "spam": 0,
            "important": 0,
            "neutral": 0,
            "uncertain": 0,
            "ai_tokens_used_today": 0,
            "ai_tokens_date": None,
        })

    def save_stats(self, account_id: str, stats: dict) -> None:
        self._write_json(self._stats_path(account_id), stats)
