# services/content.py
from sqlalchemy import select
from typing import Dict

from database.models import BotContent
from database.session import AsyncSessionLocal
from config import SECTION_NAMES
# Глобальный кэш
_content_cache: Dict[str, str] | None = None

async def _load_content() -> Dict[str, str]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(BotContent))
        rows = result.scalars().all()
        return {row.key: row.value for row in rows}

async def get_bot_content(force_refresh: bool = False) -> Dict[str, str]:
    global _content_cache
    if force_refresh or _content_cache is None:
        _content_cache = await _load_content()
    return _content_cache

async def get_content(key: str, default: str = "Информация временно недоступна") -> str:
    content = await get_bot_content()
    return content.get(key, default)

def clear_content_cache() -> None:
    global _content_cache
    _content_cache = None



  # или откуда у вас SECTION_NAMES

async def init_bot_content():
    default_texts = {
        "appointment": (
            "<b>📅 Запись на приём</b>\n\n"
            "Чтобы записаться, напишите нам в WhatsApp — мы подберём удобное время:\n"
            "<a href=\"https://wa.me/996XXXXXXXXX\">Написать в WhatsApp</a>\n\n"
            "Или позвоните: +996 XXX XXX XX XX"
        ),
        "shop_address": (
            "<b>🕐 График и адрес</b>\n\n"
            "📍 г. Бишкек, ул. Киевская, 123\n"
            "🕐 Пн–Пт: 10:00–20:00\n"
            "Сб–Вс: 10:00–18:00\n"
            "📞 +996 XXX XXX XX XX"
        ),
        "promotions": (
            "<b>🎁 Акции и новости</b>\n\n"
            "• Скидка 20% на солнцезащитные очки\n"
            "• Бесплатная проверка зрения\n"
            "• Новинки каждую неделю"
        ),
        "catalog": (
            "<b>🕶 Каталог оправ</b>\n\n"
            "Посмотрите актуальные модели в Instagram:\n"
            "<a href=\"https://instagram.com/optika_kg\">@optika_kg</a>"
        ),
        "about_shop": (
            "<b>🏥 О магазине</b>\n\n"
            "Мы — оптика с 10-летним опытом. Подбор очков, линз, диагностика зрения.\n"
            "Изготовление очков за 1 час."
        ),
        "faq": (
            "<b>❓ Поддержка и FAQ</b>\n\n"
            "• Сколько стоит проверка зрения? — Бесплатно при покупке.\n"
            "• Можно сделать очки за день? — Да.\n"
            "• Есть гарантия? — 1 год.\n\n"
            "Не нашли ответ? Напишите нам!"
        ),
    }

    async with AsyncSessionLocal() as session:
        for key, text in default_texts.items():
            result = await session.execute(select(BotContent).where(BotContent.key == key))
            if not result.scalar_one_or_none():
                session.add(BotContent(key=key, value=text))
        await session.commit()

    from services.content import clear_content_cache
    clear_content_cache()  # обновляем кэш