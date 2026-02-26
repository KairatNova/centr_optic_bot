import asyncio
import logging
import os
import shutil
import sys
import time

import psutil
#import resource

from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, CallbackQuery, FSInputFile, Message
from sqlalchemy import func, select

from config import AUTO_BACKUP_INTERVAL_HOURS, AUTO_BACKUP_TARGET_IDS, OWNER_IDS
from database.models import Person, Vision
from database.session import AsyncSessionLocal
from keyboards.owner_kb import get_dev_panel_keyboard, get_owner_main_keyboard
from middlewares.metrics import metrics_registry
from utils.audit import AUDIT_LOG_PATH, write_audit_event
from utils.backup_service import create_backup_file, get_latest_backup
from utils.broadcast_monitor import request_cancel as broadcast_request_cancel, snapshot as broadcast_snapshot


dev_panel_router = Router()
START_TIME = time.monotonic()
logger = logging.getLogger(__name__)
DB_PATH = Path("data") / "database.db"


def is_owner(user_id: int) -> bool:
    return user_id in OWNER_IDS


def _resolve_log_file_path() -> Path:
    for handler in logging.getLogger().handlers:
        if isinstance(handler, RotatingFileHandler):
            return Path(handler.baseFilename)
    return Path("logs") / "bot.log"


def _tail_lines(path: Path, limit: int) -> str:
    text = path.read_text(encoding="utf-8", errors="ignore")
    return "\n".join(text.splitlines()[-limit:])






def _ram_mb() -> float:
    """
    Возвращает объём резидентной памяти текущего процесса в MiB.
    Работает на Windows, Linux, macOS.
    """
    try:
        process = psutil.Process()
        rss_bytes = process.memory_info().rss
        return rss_bytes / (1024 * 1024)          # байты → MiB
    except Exception as e:
        # На случай очень редких ошибок (права, etc.)
        print(f"Не удалось получить использование памяти: {e}", file=sys.stderr)
        return 0.0

async def _guard_owner(callback: CallbackQuery) -> bool:
    if not is_owner(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return False
    return True


async def _restart_process() -> None:
    await asyncio.sleep(1)
    os.execv(sys.executable, [sys.executable, *sys.argv])


@dev_panel_router.message(Command("dev"))
async def cmd_dev_panel(message: Message):
    if not is_owner(message.from_user.id):
        return
    await message.answer("🛠 <b>Панель разработчика</b>\n\nВыберите действие:", reply_markup=get_dev_panel_keyboard())


@dev_panel_router.callback_query(F.data == "owner_dev_panel")
async def open_dev_panel(callback: CallbackQuery):
    if not await _guard_owner(callback):
        return
    await callback.message.answer("🛠 <b>Панель разработчика</b>\n\nВыберите действие:", reply_markup=get_dev_panel_keyboard())
    await callback.answer()


@dev_panel_router.callback_query(F.data == "dev_status")
async def dev_status(callback: CallbackQuery):
    if not await _guard_owner(callback):
        return

    uptime_seconds = int(time.monotonic() - START_TIME)
    h, rem = divmod(uptime_seconds, 3600)
    m, s = divmod(rem, 60)
    log_path = _resolve_log_file_path()
    rpm = await metrics_registry.events_per_minute()

    text = (
        "✅ <b>Статус бота</b>\n"
        f"• PID: <code>{os.getpid()}</code>\n"
        f"• Uptime: <code>{h:02d}:{m:02d}:{s:02d}</code>\n"
        f"• RAM: <b>{_ram_mb():.1f} MB</b>\n"
        f"• Update rate: <b>{rpm} / мин</b>\n"
        f"• Автобекап: каждые <b>{AUTO_BACKUP_INTERVAL_HOURS}</b> ч\n"
        f"• Кому шлём автобекап: <code>{', '.join(map(str, AUTO_BACKUP_TARGET_IDS))}</code>\n"
        f"• Лог-файл: <code>{log_path}</code>\n"
        f"• Файл существует: <b>{'да' if log_path.exists() else 'нет'}</b>"
    )
    await callback.message.answer(text, reply_markup=get_dev_panel_keyboard())
    await callback.answer()


@dev_panel_router.callback_query(F.data == "dev_restart_bot")
async def dev_restart_bot(callback: CallbackQuery):
    if not await _guard_owner(callback):
        return
    write_audit_event(callback.from_user.id, "owner", "restart_requested")
    await callback.message.answer("♻ Перезапуск бота через 1 секунду...")
    await callback.answer("Restarting")
    asyncio.create_task(_restart_process())


@dev_panel_router.callback_query(F.data == "dev_db_stats")
async def dev_db_stats(callback: CallbackQuery):
    if not await _guard_owner(callback):
        return

    async with AsyncSessionLocal() as session:
        users_count = await session.scalar(select(func.count(Person.id)))
        visions_count = await session.scalar(select(func.count(Vision.id)))
        owners_count = await session.scalar(select(func.count(Person.id)).where(Person.role == "owner"))
        admins_count = await session.scalar(select(func.count(Person.id)).where(Person.role == "admin"))

    text = (
        "📊 <b>Статистика БД</b>\n"
        f"• Пользователей: <b>{users_count or 0}</b>\n"
        f"• Записей зрения: <b>{visions_count or 0}</b>\n"
        f"• Владельцев: <b>{owners_count or 0}</b>\n"
        f"• Админов: <b>{admins_count or 0}</b>"
    )
    await callback.message.answer(text, reply_markup=get_dev_panel_keyboard())
    await callback.answer()


@dev_panel_router.callback_query(F.data == "dev_broadcast_status")
async def dev_broadcast_status(callback: CallbackQuery):
    if not await _guard_owner(callback):
        return
    snap = broadcast_snapshot()
    await callback.message.answer(
        "📨 <b>Статус рассылки</b>\n"
        f"• Running: <b>{'да' if snap['running'] else 'нет'}</b>\n"
        f"• Sent/Total: <b>{snap['sent']}/{snap['total']}</b>\n"
        f"• Errors: <b>{snap['errors']}</b>\n"
        f"• Cancel requested: <b>{'да' if snap['cancel_requested'] else 'нет'}</b>\n"
        f"• Elapsed: <b>{snap['elapsed_seconds']} сек</b>",
        reply_markup=get_dev_panel_keyboard(),
    )
    await callback.answer()


@dev_panel_router.callback_query(F.data == "dev_broadcast_stop")
async def dev_broadcast_stop(callback: CallbackQuery):
    if not await _guard_owner(callback):
        return
    broadcast_request_cancel()
    write_audit_event(callback.from_user.id, "owner", "broadcast_stop_requested")
    await callback.message.answer("⛔ Запрос на остановку рассылки отправлен.", reply_markup=get_dev_panel_keyboard())
    await callback.answer("OK")


@dev_panel_router.callback_query(F.data == "dev_health_check")
async def dev_health_check(callback: CallbackQuery):
    if not await _guard_owner(callback):
        return

    log_path = _resolve_log_file_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.touch(exist_ok=True)
    logger.info("DEV_PANEL_HEALTH_CHECK requested by owner_id=%s", callback.from_user.id)

    await callback.message.answer("🧪 Health-check выполнен: записал тестовую строку в лог.", reply_markup=get_dev_panel_keyboard())
    await callback.answer("OK")


@dev_panel_router.callback_query(F.data == "dev_get_logs")
async def dev_get_logs(callback: CallbackQuery):
    if not await _guard_owner(callback):
        return

    log_path = _resolve_log_file_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.touch(exist_ok=True)

    tail_text = _tail_lines(log_path, 400)
    if not tail_text.strip():
        await callback.message.answer("Лог-файл пуст. Нажмите «🧪 Health-check», затем попробуйте снова.", reply_markup=get_dev_panel_keyboard())
        await callback.answer()
        return

    file = BufferedInputFile(tail_text.encode("utf-8", errors="ignore"), filename="bot-log-tail.txt")
    await callback.message.answer_document(document=file, caption="📄 Последние 400 строк логов")
    await callback.message.answer("Готово ✅", reply_markup=get_dev_panel_keyboard())
    await callback.answer()


@dev_panel_router.callback_query(F.data == "dev_get_errors")
async def dev_get_errors(callback: CallbackQuery):
    if not await _guard_owner(callback):
        return

    log_path = _resolve_log_file_path()
    if not log_path.exists():
        await callback.message.answer("Лог-файл не найден.", reply_markup=get_dev_panel_keyboard())
        await callback.answer()
        return

    text = log_path.read_text(encoding="utf-8", errors="ignore")
    error_lines = [line for line in text.splitlines() if " ERROR " in line or " CRITICAL " in line]
    if not error_lines:
        await callback.message.answer("Ошибок в логах не найдено ✅", reply_markup=get_dev_panel_keyboard())
        await callback.answer()
        return

    tail_errors = "\n".join(error_lines[-200:])
    file = BufferedInputFile(tail_errors.encode("utf-8", errors="ignore"), filename="bot-log-errors.txt")
    await callback.message.answer_document(document=file, caption="🚨 Последние ERROR/CRITICAL")
    await callback.answer()


@dev_panel_router.callback_query(F.data == "dev_get_audit")
async def dev_get_audit(callback: CallbackQuery):
    if not await _guard_owner(callback):
        return

    AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    AUDIT_LOG_PATH.touch(exist_ok=True)
    text = _tail_lines(AUDIT_LOG_PATH, 500)
    if not text.strip():
        await callback.message.answer("Audit-log пуст.", reply_markup=get_dev_panel_keyboard())
        await callback.answer()
        return

    file = BufferedInputFile(text.encode("utf-8", errors="ignore"), filename="audit-log-tail.jsonl")
    await callback.message.answer_document(document=file, caption="🧾 Последние 500 записей audit-log")
    await callback.answer()


@dev_panel_router.callback_query(F.data == "dev_backup_db")
async def dev_backup_db(callback: CallbackQuery):
    if not await _guard_owner(callback):
        return

    try:
        backup_path = create_backup_file()
    except FileNotFoundError:
        await callback.message.answer("Файл БД не найден.", reply_markup=get_dev_panel_keyboard())
        await callback.answer()
        return

    write_audit_event(callback.from_user.id, "owner", "db_backup_created", {"file": str(backup_path)})
    await callback.message.answer(f"✅ Backup создан: <code>{backup_path}</code>", reply_markup=get_dev_panel_keyboard())
    await callback.message.answer_document(document=FSInputFile(backup_path), caption="💾 Backup БД")
    await callback.answer()


@dev_panel_router.callback_query(F.data == "dev_download_latest_backup")
async def dev_download_latest_backup(callback: CallbackQuery):
    if not await _guard_owner(callback):
        return

    latest = get_latest_backup()
    if latest is None:
        await callback.message.answer("Нет backup-файлов.", reply_markup=get_dev_panel_keyboard())
        await callback.answer()
        return

    await callback.message.answer_document(document=FSInputFile(latest), caption=f"📦 Последний backup: {latest.name}")
    await callback.answer()


@dev_panel_router.callback_query(F.data == "dev_restore_last_backup")
async def dev_restore_last_backup(callback: CallbackQuery):
    if not await _guard_owner(callback):
        return

    latest = get_latest_backup()
    if latest is None:
        await callback.message.answer("Нет backup-файлов для восстановления.", reply_markup=get_dev_panel_keyboard())
        await callback.answer()
        return

    shutil.copy2(latest, DB_PATH)
    write_audit_event(callback.from_user.id, "owner", "db_restore_from_backup", {"file": str(latest)})
    await callback.message.answer(
        f"♻ Восстановлено из: <code>{latest}</code>\nРекомендуется перезапустить бота.",
        reply_markup=get_dev_panel_keyboard(),
    )
    await callback.answer("OK")


@dev_panel_router.callback_query(F.data == "dev_back")
async def dev_back(callback: CallbackQuery):
    if not await _guard_owner(callback):
        return

    await callback.message.answer("👑 <b>Панель владельца</b>\n\nВыберите нужный раздел:", reply_markup=get_owner_main_keyboard())
    await callback.answer()
