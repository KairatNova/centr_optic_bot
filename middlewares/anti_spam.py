import asyncio
import time
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional, Set, Tuple

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject


class RateLimitMiddleware(BaseMiddleware):
    """Защита от спама с эскалацией: предупреждения -> временный мут."""

    def __init__(
        self,
        interval_seconds: float = 1.0,
        warning_cooldown_seconds: float = 5.0,
        warnings_before_mute: int = 3,
        warning_window_seconds: float = 60.0,
        mute_durations_seconds: Optional[List[int]] = None,
        exempt_user_ids: Optional[Iterable[int]] = None,
    ) -> None:
        self.interval_seconds = interval_seconds
        self.warning_cooldown_seconds = warning_cooldown_seconds
        self.warnings_before_mute = warnings_before_mute
        self.warning_window_seconds = warning_window_seconds
        self.mute_durations_seconds = mute_durations_seconds or [300, 3600]
        self.exempt_user_ids: Set[int] = set(exempt_user_ids or [])

        self._last_event_at: Dict[Tuple[int, str], float] = {}
        self._last_warning_at: Dict[Tuple[int, str], float] = {}

        self._warning_counts: Dict[int, int] = {}
        self._warning_window_start: Dict[int, float] = {}
        self._muted_until: Dict[int, float] = {}
        self._penalty_level: Dict[int, int] = {}

        self._lock = asyncio.Lock()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user_id = getattr(getattr(event, "from_user", None), "id", None)
        if user_id is None:
            return await handler(event, data)

        if user_id in self.exempt_user_ids:
            return await handler(event, data)

        event_kind = "callback" if isinstance(event, CallbackQuery) else "message"
        now = time.monotonic()

        should_block = False
        should_warn = False
        mute_notice: Optional[str] = None

        async with self._lock:
            mute_until = self._muted_until.get(user_id, 0.0)
            if mute_until > now:
                should_block = True
                key = (user_id, event_kind)
                last_warn = self._last_warning_at.get(key)
                if last_warn is None or (now - last_warn) >= self.warning_cooldown_seconds:
                    remain = int(mute_until - now)
                    minutes = max(1, remain // 60)
                    mute_notice = f"Вы временно ограничены за спам. Попробуйте снова через ~{minutes} мин."
                    self._last_warning_at[key] = now
            else:
                key = (user_id, event_kind)
                last_event = self._last_event_at.get(key)

                if last_event is not None and (now - last_event) < self.interval_seconds:
                    should_block = True

                    last_warn = self._last_warning_at.get(key)
                    if last_warn is None or (now - last_warn) >= self.warning_cooldown_seconds:
                        should_warn = True
                        self._last_warning_at[key] = now

                        window_start = self._warning_window_start.get(user_id)
                        if window_start is None or (now - window_start) > self.warning_window_seconds:
                            self._warning_window_start[user_id] = now
                            self._warning_counts[user_id] = 0

                        self._warning_counts[user_id] = self._warning_counts.get(user_id, 0) + 1

                        if self._warning_counts[user_id] >= self.warnings_before_mute:
                            level = self._penalty_level.get(user_id, 0)
                            duration_index = min(level, len(self.mute_durations_seconds) - 1)
                            duration = self.mute_durations_seconds[duration_index]
                            self._muted_until[user_id] = now + duration
                            self._penalty_level[user_id] = level + 1
                            self._warning_counts[user_id] = 0
                            self._warning_window_start[user_id] = now
                            mute_notice = (
                                "Слишком много попыток за короткое время. "
                                f"Доступ ограничен на {max(1, duration // 60)} мин."
                            )
                else:
                    self._last_event_at[key] = now

        if not should_block:
            return await handler(event, data)

        message_text = mute_notice
        if message_text is None and should_warn:
            message_text = "Слишком часто 🙏 Подождите секунду."

        if message_text is not None:
            if isinstance(event, CallbackQuery):
                await event.answer(message_text, show_alert=False)
            elif isinstance(event, Message):
                await event.reply(message_text)

        return None
