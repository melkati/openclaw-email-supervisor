"""Schema migrations for persistent JSON files.

Each migration is a simple function that transforms a data dict from
version *N* to version *N+1*.  :func:`migrate` applies all necessary
migrations in order.
"""

from __future__ import annotations

from typing import Callable

from email_supervisor.utils.logging_config import get_logger

log = get_logger("migrations")

# Registry: {file_kind: {from_version: migration_fn}}
_MIGRATIONS: dict[str, dict[int, Callable[[dict], dict]]] = {}


def register(kind: str, from_version: int):
    """Decorator to register a migration function."""
    def decorator(fn: Callable[[dict], dict]):
        _MIGRATIONS.setdefault(kind, {})[from_version] = fn
        return fn
    return decorator


def migrate(kind: str, data: dict) -> dict:
    """Apply all pending migrations to *data* for the given *kind*.

    The dict must contain a ``"version"`` key.  After migration the
    version is bumped to the latest known.
    """
    current = data.get("version", 1)
    migrations = _MIGRATIONS.get(kind, {})
    while current in migrations:
        log.info(
            "Migrating %s from v%d to v%d", kind, current, current + 1
        )
        data = migrations[current](data)
        current += 1
        data["version"] = current
    return data


# ── example migrations (activate when schema changes) ─────────
# @register("whitelist", from_version=1)
# def _whitelist_v1_to_v2(data: dict) -> dict:
#     """Add ``reason`` field to every entry."""
#     for entry in data.get("entries", []):
#         entry.setdefault("reason", "")
#     return data
