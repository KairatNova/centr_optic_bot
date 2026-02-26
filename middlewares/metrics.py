import asyncio
import time
from collections import deque
from typing import Any, Awaitable, Callable, Deque, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject


class RuntimeMetrics:
    def __init__(self) -> None:
        self._timestamps: Deque[float] = deque(maxlen=5000)
        self._lock = asyncio.Lock()

    async def mark_event(self) -> None:
        now = time.monotonic()
        async with self._lock:
            self._timestamps.append(now)

    async def events_per_minute(self) -> int:
        now = time.monotonic()
        border = now - 60
        async with self._lock:
            return sum(1 for ts in self._timestamps if ts >= border)


metrics_registry = RuntimeMetrics()


class MetricsMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        await metrics_registry.mark_event()
        return await handler(event, data)
