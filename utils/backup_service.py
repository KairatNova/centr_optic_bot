import asyncio
import logging
from datetime import datetime
from pathlib import Path
from shutil import copy2

from aiogram import Bot
from aiogram.types import FSInputFile

from utils.audit import write_audit_event

logger = logging.getLogger(__name__)
DB_PATH = Path("data") / "database.db"
BACKUP_DIR = Path("backups")


def create_backup_file() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    if not DB_PATH.exists():
        raise FileNotFoundError(f"DB file not found: {DB_PATH}")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"database_{stamp}.db"
    copy2(DB_PATH, backup_path)
    return backup_path


def get_latest_backup() -> Path | None:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backups = sorted(BACKUP_DIR.glob("database_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    return backups[0] if backups else None


async def auto_backup_worker(bot: Bot, target_ids: list[int], interval_hours: int) -> None:
    interval_seconds = max(1, interval_hours) * 3600
    logger.info("Auto-backup worker started: every %s hours, targets=%s", interval_hours, target_ids)

    while True:
        try:
            await asyncio.sleep(interval_seconds)
            backup_path = create_backup_file()
            caption = f"💾 Автобекап БД: {backup_path.name}"
            for owner_id in target_ids:
                await bot.send_document(owner_id, document=FSInputFile(backup_path), caption=caption)
            write_audit_event(0, "system", "auto_backup_sent", {"file": str(backup_path), "targets": target_ids})
        except asyncio.CancelledError:
            logger.info("Auto-backup worker cancelled")
            raise
        except Exception as e:
            logger.error("Auto-backup failed: %s", e, exc_info=True)
