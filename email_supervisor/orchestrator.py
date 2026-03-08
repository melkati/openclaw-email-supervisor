"""Account orchestrator — multi-account asyncio lifecycle manager.

Creates and manages one :class:`AccountWorker` per configured IMAP
account.  Each worker runs as an independent asyncio task with its own
IMAP connection, pipeline, learning engine, and store.

The orchestrator provides:
- Parallel account processing
- Per-account error isolation
- Pause / resume / reload per account
- Aggregated health reporting
"""

from __future__ import annotations

import asyncio
import glob
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from email_supervisor.ai.gateway import AIGateway
from email_supervisor.imap_client import IMAPClient, IMAPClientError
from email_supervisor.learning.engine import LearningEngine
from email_supervisor.models.account_config import AccountConfig
from email_supervisor.notifications.dispatcher import NotificationDispatcher
from email_supervisor.notifications.telegram_notifier import TelegramNotifier
from email_supervisor.persistence.json_store import JSONStore
from email_supervisor.persistence.store import AccountStore
from email_supervisor.pipeline import EmailPipeline
from email_supervisor.utils.constants import DEFAULT_MAX_PROCESSED_IDS
from email_supervisor.utils.logging_config import get_logger

log = get_logger("orchestrator")


class AccountWorker:
    """Async worker for a single IMAP account."""

    def __init__(
        self,
        config: AccountConfig,
        store: AccountStore,
        pipeline: EmailPipeline,
        imap: IMAPClient,
        learning: Optional[LearningEngine] = None,
    ) -> None:
        self.config = config
        self.store = store
        self.pipeline = pipeline
        self.imap = imap
        self.learning = learning

        self._running = False
        self._paused = False
        self._task: Optional[asyncio.Task] = None
        self._check_event = asyncio.Event()

    @property
    def account_id(self) -> str:
        return self.config.account_id

    @property
    def is_running(self) -> bool:
        return self._running and not self._paused

    async def start(self) -> None:
        """Start the worker loop as an asyncio task."""
        self._running = True
        self._task = asyncio.create_task(
            self._run_loop(), name=f"worker-{self.account_id}"
        )
        log.info("Started worker for %s", self.account_id)

    async def stop(self) -> None:
        """Gracefully stop the worker."""
        self._running = False
        self._check_event.set()  # unblock any wait
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self.imap.disconnect()
        log.info("Stopped worker for %s", self.account_id)

    def pause(self) -> None:
        self._paused = True
        log.info("Paused %s", self.account_id)

    def resume(self) -> None:
        self._paused = False
        self._check_event.set()
        log.info("Resumed %s", self.account_id)

    def trigger_check(self) -> None:
        """Force an immediate check cycle."""
        self._check_event.set()

    async def _run_loop(self) -> None:
        """Main worker loop: connect → fetch → pipeline → sleep → repeat."""
        while self._running:
            if self._paused:
                await self._wait_or_sleep(30)
                continue

            try:
                # Ensure connection
                if not self.imap.is_connected:
                    await self.imap.connect()

                # Process each configured folder
                for folder in self.config.imap.folders:
                    await self._process_folder(folder)

                # Periodic compaction
                self.store.compact_processed(
                    self.account_id,
                    max_entries=DEFAULT_MAX_PROCESSED_IDS,
                    max_age_s=self.config.polling.max_age_hours * 3600 * 2,
                )

            except IMAPClientError as exc:
                # Auth error — stop retrying
                log.error(
                    "Auth/permanent error for %s: %s — disabling account",
                    self.account_id, exc,
                )
                self._paused = True
                continue

            except Exception as exc:
                log.warning(
                    "Error in worker %s: %s — will reconnect",
                    self.account_id, exc,
                )
                try:
                    await self.imap.reconnect()
                except Exception:
                    pass

            # Wait for next cycle
            await self._wait_or_sleep(self.config.polling.interval_seconds)

    async def _process_folder(self, folder: str) -> None:
        """Fetch and process new emails from a single IMAP folder."""
        since = datetime.now(timezone.utc) - timedelta(
            hours=self.config.polling.max_age_hours
        )
        uids = await self.imap.fetch_new_uids(folder=folder, since=since)
        if not uids:
            return

        # Limit batch size
        uids = uids[: self.config.polling.batch_size]

        # Fetch headers
        messages = await self.imap.fetch_headers(uids)
        for msg in messages:
            msg.folder = folder

        if not messages:
            return

        log.info(
            "Fetched %d new emails from %s/%s",
            len(messages), self.account_id, folder,
            extra={"account": self.account_id},
        )

        # Run pipeline
        await self.pipeline.process_batch(messages)

    async def _wait_or_sleep(self, seconds: int) -> None:
        """Wait for the check event or timeout."""
        self._check_event.clear()
        try:
            await asyncio.wait_for(self._check_event.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass


class AccountOrchestrator:
    """Manage multiple AccountWorkers."""

    def __init__(
        self,
        config_root: str | Path,
        data_root: str | Path,
        telegram_chat_ids: Optional[list[int | str]] = None,
    ) -> None:
        self._config_root = Path(config_root)
        self._data_root = Path(data_root)
        self._telegram_chats = telegram_chat_ids or []

        self._store = JSONStore(data_root=self._data_root, config_root=self._config_root)
        self._workers: dict[str, AccountWorker] = {}

        # Shared AI gateway
        self._ai_gateway = AIGateway(store=self._store)

        # Shared notification dispatcher
        telegram = TelegramNotifier(chat_ids=self._telegram_chats) if self._telegram_chats else None
        self._notifier = NotificationDispatcher(
            telegram=telegram,
            enabled_channels=["telegram"] if telegram else [],
        )

    async def start_all(self) -> None:
        """Discover accounts and start a worker for each."""
        accounts_dir = self._config_root / "accounts"
        if not accounts_dir.exists():
            log.warning("No accounts directory found at %s", accounts_dir)
            return

        for path in sorted(accounts_dir.glob("*.json")):
            if path.name.startswith("_"):
                continue  # skip templates
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                log.debug(f"Raw account config: {raw}")
                config = AccountConfig.from_dict(raw)
                log.debug(f"Loaded account config: {config}")
                if not config.enabled:
                    log.info("Skipping disabled account %s", config.account_id)
                    continue
                await self._start_worker(config)
            except Exception as exc:
                log.error("Failed to load account %s: %s", path.name, exc)

        log.info("Orchestrator started with %d accounts", len(self._workers))

    async def stop_all(self) -> None:
        """Stop all workers gracefully."""
        for worker in self._workers.values():
            await worker.stop()
        self._workers.clear()
        log.info("All workers stopped")

    async def _start_worker(self, config: AccountConfig) -> None:
        """Create and start a worker for one account."""
        imap = IMAPClient(config.imap, config.account_id)

        learning = LearningEngine(
            store=self._store,
            account_id=config.account_id,
            config=config.learning,
            notifier=self._notifier,
        ) if config.learning.enabled else None

        pipeline = EmailPipeline(
            config=config,
            store=self._store,
            ai_gateway=self._ai_gateway,
            learning_engine=learning,
            notifier=self._notifier,
        )

        worker = AccountWorker(
            config=config,
            store=self._store,
            pipeline=pipeline,
            imap=imap,
            learning=learning,
        )

        self._workers[config.account_id] = worker
        await worker.start()

    # ── control API (used by Telegram ConfigManager) ──────────

    def list_accounts(self) -> list[dict[str, Any]]:
        """Return status info for all accounts."""
        return [
            {
                "id": w.account_id,
                "display_name": w.config.display_name,
                "running": w.is_running,
            }
            for w in self._workers.values()
        ]

    def pause_account(self, account_id: str) -> None:
        if account_id in self._workers:
            self._workers[account_id].pause()

    def resume_account(self, account_id: str) -> None:
        if account_id in self._workers:
            self._workers[account_id].resume()

    def trigger_check(self, account_id: str) -> None:
        if account_id in self._workers:
            self._workers[account_id].trigger_check()

    def reload_pipeline(self, account_id: str) -> None:
        if account_id in self._workers:
            self._workers[account_id].pipeline.reload_rules()
