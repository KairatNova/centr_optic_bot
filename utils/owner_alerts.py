import asyncio
import logging
import time
from typing import Iterable

from aiogram import Bot


class OwnerAlertHandler(logging.Handler):
    def __init__(
        self,
        owner_ids: Iterable[int],
        min_interval_seconds: float = 30.0,
        critical_owner_id: int | None = None,
    ) -> None:
        super().__init__(level=logging.ERROR)
        self.owner_ids = list(owner_ids)
        self.min_interval_seconds = min_interval_seconds
        self.critical_owner_id = critical_owner_id
        self._last_sent_at = 0.0
        self.bot: Bot | None = None

    def bind_bot(self, bot: Bot) -> None:
        self.bot = bot

    def emit(self, record: logging.LogRecord) -> None:
        if self.bot is None:
            return
        now = time.monotonic()
        if (now - self._last_sent_at) < self.min_interval_seconds:
            return

        self._last_sent_at = now
        text = self.format(record)
        short = text[-3500:]
        message = f"🚨 <b>{record.levelname}</b>\n<code>{short}</code>"

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        target_owner_ids = self.owner_ids
        if record.levelno >= logging.CRITICAL and self.critical_owner_id is not None:
            target_owner_ids = [self.critical_owner_id]

        for owner_id in target_owner_ids:
            loop.create_task(self.bot.send_message(owner_id, message))