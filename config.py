import os
from dotenv import load_dotenv, find_dotenv
from typing import List

load_dotenv(find_dotenv())


SECTION_NAMES = {
    "appointment": "📅 Запись на приём",
    "shop_address": "🕐 График и адрес",
    "promotions": "🎁 Акции и новости",
    "catalog": "🕶 Каталог оправ",
    "about_shop": "🏥 О магазине",
    "faq": "❓ Поддержка и FAQ",
}

def _get_required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Environment variable {name} is required")
    return value


def _parse_id_list(raw_value: str) -> List[int]:
    values: List[int] = []
    for item in raw_value.split(","):
        item = item.strip()
        if not item:
            continue
        if not item.isdigit():
            raise RuntimeError(f"Invalid integer value in ID list: {item}")
        values.append(int(item))
    return values


BOT_TOKEN = _get_required_env("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///data/database.db")

OWNER_IDS = _parse_id_list(_get_required_env("OWNER_IDS"))


AUTO_BACKUP_INTERVAL_HOURS = int(os.getenv("AUTO_BACKUP_INTERVAL_HOURS", "24"))
AUTO_BACKUP_TARGET_IDS = _parse_id_list(os.getenv("AUTO_BACKUP_TARGET_IDS", "")) or OWNER_IDS